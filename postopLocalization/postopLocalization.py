import os
import sys
import shutil
import numpy as np
import json
import vtk, qt, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

if getattr(sys, 'frozen', False):
	cwd = os.path.dirname(sys.argv[0])
elif __file__:
	cwd = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.dirname(cwd))

from helpers.helpers import plotLead, rotation_matrix, warningBox, vtkModelBuilderClass,\
getPointCoords,adjustPrecision,getMarkupsNode, addCustomLayouts, frame_angles, plotMicroelectrode

from helpers.variables import fontSetting, groupboxStyle, coordSys, slicerLayout, electrodeModels, microelectrodeModels

#
# postopLocalization
#

class postopLocalization(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "07: Postop Localization"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = []
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#postopLocalization">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# postopLocalizationWidget
#

class postopLocalizationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
	"""Uses ScriptedLoadableModuleWidget base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent=None):
		"""
		Called when the user opens the module the first time and the widget is initialized.
		"""
		ScriptedLoadableModuleWidget.__init__(self, parent)
		VTKObservationMixin.__init__(self)  # needed for parameter node observation
		self.logic = None
		self._parameterNode = None
		self._updatingGUIFromParameterNode = False
		
		self.active = False
		
		self.postActualElecPlot = True
		self.postActualMERTracksPlot = True
		self.postImplantTraj = []
		self.postElecModelLastButton = None

	def setup(self):
		"""
		Called when the user opens the module the first time and the widget is initialized.
		"""
		ScriptedLoadableModuleWidget.setup(self)

		self._loadUI()

		# Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
		# "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
		# "setMRMLScene(vtkMRMLScene*)" slot.
		

		# Create logic class. Logic implements all computations that should be possible to run
		# in batch mode, without a graphical user interface.
		self.logic = postopLocalizationLogic()

		self.setupMarkupNodes()

		# Connections
		self._setupConnections()

	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/postopLocalization.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)

		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
		fontSettings = qt.QFont(fontSetting)
		fontSettings.setBold(False)
		self.ui.planNameGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.planNameGB.setFont(fontSettings)
		self.ui.postElecModelGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.postElecModelGB.setFont(fontSettings)
		self.ui.postTrajUsedGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.postTrajUsedGB.setFont(fontSettings)
		self.ui.postElecPositionGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.postElecPositionGB.setFont(fontSettings)

		self.ui.postElecCB.addItems(['Select Electrode']+list(electrodeModels))
		self.ui.postElecCB.setCurrentIndex(self.ui.postElecCB.findText('Select Electrode'))
		self.ui.postMicroModel.addItems(['None']+list(microelectrodeModels['probes']))
		self.ui.postMicroModel.setCurrentIndex(self.ui.postMicroModel.findText('None'))

	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		
		self.ui.planAdd.connect('clicked(bool)', self.onPlanAdd)
		self.ui.planDelete.connect('clicked(bool)', self.onPlanDelete)
		self.ui.planAddConfirm.connect('clicked(bool)', self.onPlanAddConfirm)
		self.ui.planNameEdit.connect('returnPressed()', self.ui.planAddConfirm.click)
		self.ui.planName.connect('currentIndexChanged(int)', self.onPlanChange)
		self.ui.planAddConfirm.setVisible(0)
		not_resize = self.ui.planAddConfirm.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planAddConfirm.setSizePolicy(not_resize)
		self.ui.planNameEdit.setVisible(0)
		self.ui.planName.connect('currentIndexChanged(int)', self.onPlanChange)
		self.ui.trajUsedButtonGroup.connect('buttonClicked(int)', self.onTrajUsedButtonGroup)
		self.ui.hideDataButtonGroup.buttonClicked.connect(self.onToggleDataButton)
		self.ui.unlockButtonGroup.buttonClicked.connect(self.onButtonClick)
		self.ui.jumpToButtonGroup.buttonClicked.connect(self.onButtonClick)
		self.ui.postShowActualElecButtonGroup.connect('buttonClicked(int)', self.onPostActualElecButtonGroupClicked)
		self.ui.postShowActualMERTracksGroup.connect('buttonClicked(int)', self.onPostActualMERTracksButtonClicked)
		self.ui.postElecConfirmButton.connect('clicked(bool)', self.onActualElecPlotButton)
		
		# Make sure parameter node is initialized (needed for module reload)
		self.initializeParameterNode()

		self.logic.addCustomLayouts()

	def cleanup(self):
		"""
		Called when the application closes and the module widget is destroyed.
		"""
		self.removeObservers()

	def enter(self):
		"""
		Called each time the user opens this module.
		"""
		# Make sure parameter node exists and observed
		self.initializeParameterNode()
		self.active = True
		self.resetValues()
	
	def exit(self):
		"""
		Called each time the user opens a different module.
		"""
		# Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
		self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

	def onSceneStartClose(self, caller, event):
		"""
		Called just before the scene is closed.
		"""
		# Parameter node will be reset, do not use it anymore
		self.setParameterNode(None)

	def onSceneEndClose(self, caller, event):
		"""
		Called just after the scene is closed.
		"""
		# If this module is shown while the scene is closed then recreate a new parameter node immediately
		if self.parent.isEntered:
			self.initializeParameterNode()

	def initializeParameterNode(self):
		"""
		Ensure parameter node exists and observed.
		"""
		# Parameter node stores all user choices in parameter values, node selections, etc.
		# so that when the scene is saved and reloaded, these settings are restored.

		self.setParameterNode(self.logic.getParameterNode())

		# Select default input nodes if nothing is selected yet to save a few clicks for the user
		#if not self._parameterNode.GetNodeReference("InputVolume"):
		#	firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
		#	if firstVolumeNode:
		#		self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

	def setParameterNode(self, inputParameterNode):
		"""
		Set and observe parameter node.
		Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
		"""

		if inputParameterNode:
			self.logic.setDefaultParameters(inputParameterNode)

		# Unobserve previously selected parameter node and add an observer to the newly selected.
		# Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
		# those are reflected immediately in the GUI.
		if self._parameterNode is not None:
			self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
		self._parameterNode = inputParameterNode
		if self._parameterNode is not None:
			self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

		# Initial GUI update
		self.updateGUIFromParameterNode()

	def updateGUIFromParameterNode(self, caller=None, event=None):
		"""
		This method is called whenever parameter node is changed.
		The module GUI is updated to show the current state of the parameter node.
		"""

		if self._parameterNode is None or self._updatingGUIFromParameterNode:
			return

		# Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
		self._updatingGUIFromParameterNode = True

		if self._parameterNode.GetParameter('derivFolder'):

			planNames = [self.ui.planName.itemText(i) for i in range(self.ui.planName.count)]

			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as surgical_info:
				surgical_info_json = json.load(surgical_info)

			plansAdd = [x for x in list(surgical_info_json['trajectories']) if x not in planNames]
			self.ui.planName.addItems(plansAdd)

		# All the GUI updates are done
		self._updatingGUIFromParameterNode = False

	def updateParameterNodeFromGUI(self, caller=None, event=None):
		"""
		This method is called when the user makes any change in the GUI.
		The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
		"""

		if self._parameterNode is None or self._updatingGUIFromParameterNode:
			return

		#wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch
		#self._parameterNode.EndModify(wasModified)

	def setupMarkupNodes(self):
		self.markupsLogic = slicer.modules.markups.logic()
		
		self.ui.botPoint.setMRMLScene(slicer.mrmlScene)
		self.ui.botPoint.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.botPoint.placeButton().show()
		self.ui.botPoint.deleteButton().show()
		
		self.ui.topPoint.setMRMLScene(slicer.mrmlScene)
		self.ui.topPoint.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.topPoint.placeButton().show()
		self.ui.topPoint.deleteButton().show()

	def onToggleDataButton(self, button):
		if self.ui.planName.currentText != '':
			if button.text.lower() == 'yes':
				visibilityOpp = 0
				visibility = 1
			else:
				visibilityOpp = 1
				visibility = 1

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if self.ui.planName.currentText in imodel.GetName():
					if 'ses-post' in imodel.GetName():
						imodel.GetDisplayNode().SetVisibility(visibility)
					elif f"ses-pre_task-{self.ui.planName.currentText}" in imodel.GetName():
						imodel.GetDisplayNode().SetVisibility(visibilityOpp)
					elif f"ses-intra_task-{self.ui.planName.currentText}" in imodel.GetName():
						imodel.GetDisplayNode().SetVisibility(visibilityOpp)

			#lineNode = getMarkupsNode((self.ui.planName.currentText + '_line'), node_type='vtkMRMLMarkupsLineNode')
			#if lineNode is not None:
			#	lineNode.GetDisplayNode().SetVisibility(visibilityOpp)
			#
			#lineNode = getMarkupsNode((self.ui.planName.currentText + '_line_intra'), node_type='vtkMRMLMarkupsLineNode')
			#if lineNode is not None:
			#	lineNode.GetDisplayNode().SetVisibility(visibilityOpp)

	def onTrajUsedButtonGroup(self, button):
		"""
		Slot for selection of ``Trajectory used`` under ``Left Plan``
		
		"""
		children = self.ui.postTrajUsedGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked():
				self.postImplantTraj = i.text.lower()
			i.checked = False

		button_idx = abs(button - -2)
		if children[button_idx].text.lower() != self.postImplantTraj:
			if self.postImplantTraj:
				children[button_idx].setChecked(True)
				self.postImplantTraj = []
			else:
				children[button_idx].setChecked(False)
				self.postImplantTraj = children[button_idx].text.lower()
		elif children[button_idx].text.lower() == self.postImplantTraj:
			children[button_idx].setChecked(True)
			self.postImplantTraj = []

	def resetValues(self):

		self.ui.botX.value = 0.0
		self.ui.botY.value = 0.0
		self.ui.botZ.value = 0.0
		self.ui.topX.value = 0.0
		self.ui.topY.value = 0.0
		self.ui.topZ.value = 0.0

		self.ui.postElecCB.setCurrentIndex(self.ui.postElecCB.findText('Select Electrode'))

		children = self.ui.postTrajUsedGB.findChildren('QRadioButton')
		for i in children:
			i.checked = False

		#slicer.util.getNode('bot').RemoveAllControlPoints()
		#slicer.util.getNode('top').RemoveAllControlPoints()

		self.ui.actualElecPlotY.checked=True
		self.ui.actualElecPlotY.checked=True

		self.postElecModelLastButton = None

		if self.ui.planName.currentText != '' and self.ui.planName.currentText != 'Select plan':

			if len(slicer.util.getNodes('bot')) > 0:
				slicer.mrmlScene.RemoveNode(slicer.util.getNode('bot'))

			if len(slicer.util.getNodes('top')) > 0:
				slicer.mrmlScene.RemoveNode(slicer.util.getNode('top'))

			self.markupsNodeBot = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			self.markupsNodeBot.SetName('bot')
			self.markupsNodeBot.AddDefaultStorageNode()
			self.markupsNodeBot.GetStorageNode().SetCoordinateSystem(coordSys)
			self.ui.botPoint.setCurrentNode(self.markupsNodeBot)
			
			self.markupsNodeBot.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
			self.markupsNodeBot.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)

			self.markupsNodeTop = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			self.markupsNodeTop.SetName('top')
			self.markupsNodeTop.AddDefaultStorageNode()
			self.markupsNodeTop.GetStorageNode().SetCoordinateSystem(coordSys)
			self.ui.topPoint.setCurrentNode(self.markupsNodeTop)

			self.markupsNodeTop.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
			self.markupsNodeTop.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)

			modelVis=None
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if self.ui.planName.currentText in imodel.GetName():
					if any(x in imodel.GetName() for x in ('ses-pre','ses-intra')):
						if imodel.GetDisplayNode().GetVisibility()== False:
							modelVis=False
						else:
							modelVis=True

			print(modelVis)
			if modelVis is not None:
				if modelVis:
					self.ui.hideDataWig.findChild(qt.QRadioButton, 'hideDataN').setChecked(True)
				else:
					self.ui.hideDataWig.findChild(qt.QRadioButton, 'hideDataY').setChecked(True)
	
	def onPlanDelete(self):
		if self.ui.planName.currentText == '':
			warningBox('No plan selected for deletion!')
			return
		
		parent = None
		for w in slicer.app.topLevelWidgets():
			if hasattr(w,'objectName'):
				if w.objectName == 'qSlicerMainWindow':
					parent=w

		windowTitle = "Confirm plan removal"
		windowText = f"Are you sure you want to delete {self.ui.planName.currentText}"
		if parent is None:
			ret = qt.QMessageBox.question(self, windowTitle, windowText, qt.QMessageBox.Yes | qt.QMessageBox.No)
		else:
			ret = qt.QMessageBox.question(parent, windowTitle, windowText, qt.QMessageBox.Yes | qt.QMessageBox.No)
		
		if ret == qt.QMessageBox.Yes:
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
				surgical_data = json.load(surg_file)
			
			planName = self.ui.planName.currentText
			self.ui.planName.removeItem(self.ui.planName.findText(planName))
			
			if planName in list(surgical_data['trajectories']):
				surgical_data_copy = dict(surgical_data)
				del surgical_data_copy['trajectories'][planName]
				json_output = json.dumps(surgical_data_copy, indent=4)
				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json"), 'w') as (fid):
					fid.write(json_output)
					fid.write('\n')
			
			self.resetValues()
			
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if 'task-' + planName in imodel.GetName():
					os.remove(imodel.GetStorageNode().GetFileName())
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetName()))

	def onPlanAdd(self):
		if not self.ui.planNameEdit.isVisible():
			self.ui.planNameEdit.setVisible(1)
			self.ui.planAddConfirm.setVisible(1)

	def onPlanAddConfirm(self):
		if self.ui.planNameEdit.text == '':
			warningBox('Pleae enter a plan name!')
			return
		elif self.ui.planNameEdit.text in [self.ui.planName.itemText(i) for i in range(self.ui.planName.count)]:
			warningBox(f"A plan with the name {self.ui.planNameEdit.text} already exists!")
			return
		else:
			if self.ui.planNameEdit.isVisible():
				self.ui.planNameEdit.setVisible(0)
				self.ui.planAddConfirm.setVisible(0)

			self.ui.planName.addItems([self.ui.planNameEdit.text])
			self.ui.planName.setCurrentIndex(self.ui.planName.findText(self.ui.planNameEdit.text))
			self.ui.planNameEdit.clear()
			
			self.resetValues()

	def updateMERLabelOrientatrion(self,side):
		if side == 'right':
			children = self.ui.postTrajUsedGB.findChildren('QRadioButton')
			for i in children:
				if i.text == 'Lateral' and i.name == 'postLatMER':
					continue
				if i.text == 'Medial' and i.name == 'postLatMER':
					i.text = 'Lateral'
				elif i.text == 'Lateral' and i.name == 'postMedMER':
					i.text = 'Medial'
				elif i.text == 'Medial' and i.name == 'postMedMER':
					continue
		else:
			children = self.ui.postTrajUsedGB.findChildren('QRadioButton')
			for i in children:
				if i.text == 'Lateral' and i.name == 'postLatMER':
					i.text = 'Medial'
				elif i.text == 'Medial' and i.name == 'postLatMER':
					continue
				elif i.text == 'Lateral' and i.name == 'postMedMER':
					continue
				elif i.text == 'Medial' and i.name == 'postMedMER':
					i.text = 'Lateral'

	def onPlanChange(self):
		if self.active and self._parameterNode.GetParameter('derivFolder'):
			if self.ui.planName.currentText != '':

				self.resetValues()

				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
					surgical_data = json.load(surg_file)
				
				planName = self.ui.planName.currentText
				if planName in list(surgical_data['trajectories']):
					
					if 'side' in list(surgical_data['trajectories'][planName]):
						self.updateMERLabelOrientatrion(surgical_data['trajectories'][planName]['side'])

					if 'intra' in list(surgical_data['trajectories'][planName]):
						if 'lead_traj_chosen' in list(surgical_data['trajectories'][planName]['intra']):
							if surgical_data['trajectories'][planName]['intra']['lead_traj_chosen']:
								children = self.ui.postTrajUsedGB.findChildren('QRadioButton')
								for i in children:
									if i.text.lower() == surgical_data['trajectories'][planName]['intra']['lead_traj_chosen'].lower():
										i.checked = True
										self.postChans = i.text.lower()

					if 'pre' in list(surgical_data['trajectories'][planName]):
						if 'elecUsed' in list(surgical_data['trajectories'][planName]['pre']):
							if surgical_data['trajectories'][planName]['pre']['elecUsed']:
									self.ui.postElecCB.setCurrentIndex(self.ui.postElecCB.findText(surgical_data['trajectories'][planName]['pre']['elecUsed']))
									self.postElecModel = self.ui.postElecCB.currentText
						if 'microUsed' in list(surgical_data['trajectories'][planName]['pre']):
							if surgical_data['trajectories'][planName]['pre']['microUsed']:
									self.ui.postMicroModel.setCurrentIndex(self.ui.postMicroModel.findText(surgical_data['trajectories'][planName]['pre']['microUsed']))

					if 'post' in list(surgical_data['trajectories'][planName]):
						if surgical_data['trajectories'][planName]['post']['target']:
							self.ui.botX.value = surgical_data['trajectories'][planName]['post']['target'][0]
							self.ui.botY.value = surgical_data['trajectories'][planName]['post']['target'][1]
							self.ui.botZ.value = surgical_data['trajectories'][planName]['post']['target'][2]
						
						if surgical_data['trajectories'][planName]['post']['entry']:
							self.ui.topX.value = surgical_data['trajectories'][planName]['post']['entry'][0]
							self.ui.topY.value = surgical_data['trajectories'][planName]['post']['entry'][1]
							self.ui.topZ.value = surgical_data['trajectories'][planName]['post']['entry'][2]
					else:
						botPointCoords = getPointCoords((self.ui.planName.currentText + '_line_post'), 'bot', node_type='vtkMRMLMarkupsLineNode')
						if not np.array_equal(adjustPrecision(botPointCoords), adjustPrecision(np.array([0.0] * 3))):
							self.ui.botX.value = botPointCoords[0]
							self.ui.botY.value = botPointCoords[1]
							self.ui.botZ.value = botPointCoords[2]

						topPointCoords = getPointCoords((self.ui.planName.currentText + '_line_post'), 'top', node_type='vtkMRMLMarkupsLineNode')
						if not np.array_equal(adjustPrecision(topPointCoords), adjustPrecision(np.array([0.0] * 3))):
							self.ui.topX.value = topPointCoords[0]
							self.ui.topY.value = topPointCoords[1]
							self.ui.topZ.value = topPointCoords[2]

	def onPointDelete(self, caller, event):
		activeLabel = caller.GetName()
		fiducialNode = getMarkupsNode(activeLabel)
		for ifid in range(fiducialNode.GetNumberOfControlPoints()):
			if activeLabel in fiducialNode.GetNthControlPointLabel(ifid):
				fiducialNode.RemoveNthControlPoint(ifid)

		planPointOrigin = getPointCoords((self.ui.planName.currentText + '_line'), activeLabel, node_type='vtkMRMLMarkupsLineNode')
		if np.array_equal(adjustPrecision(planPointOrigin), adjustPrecision(np.array([0.0] * 3))):
			if fiducialNode is not None:
				if 'bot' in activeLabel:
					self.ui.botX.value = 0
					self.ui.botY.value = 0
					self.ui.botZ.value = 0
				elif 'top' in activeLabel:
					self.ui.topX.value = 0
					self.ui.topY.value = 0
					self.ui.topZ.value = 0

	def onPointAdd(self, caller, event):
		activeLabel = caller.GetName()

		if 'bot' in activeLabel:
			activeLabelName='target'
			activeNodeName='bot'
		elif 'top' in activeLabel:
			activeLabelName='entry'
			activeNodeName='top'

		if len(slicer.util.getNodes(self.ui.planName.currentText + '_line_post')) > 0:
			activePointCoords = getPointCoords((self.ui.planName.currentText + '_line_post'), activeLabelName, node_type='vtkMRMLMarkupsLineNode')
		else:
			if 'bot' in activeLabel:
				activePointCoords=np.array([self.ui.botX.value, self.ui.botY.value, self.ui.botZ.value])
			elif 'top' in activeLabel:
				activePointCoords=np.array([self.ui.topX.value, self.ui.topY.value, self.ui.topZ.value])

		definePoint=True
		if not np.array_equal(adjustPrecision(activePointCoords), adjustPrecision(np.array([0.0] * 3))):
			qm = qt.QMessageBox()
			ret = qm.question(self, '', f"Are you sure you want to re-define {activeLabel} point for plan {self.ui.planName.currentText}?", qm.Yes | qm.No)
			if ret == qm.No:
				definePoint=False
				slicer.util.getNode(activeNodeName).RemoveAllControlPoints()


		if definePoint:
			movingMarkupIndex = caller.GetDisplayNode().GetActiveControlPoint()
			for ifid in range(caller.GetNumberOfControlPoints()):
				if activeLabel in caller.GetNthControlPointLabel(ifid):
					activePointCoords = [0]*3
					caller.GetNthControlPointPositionWorld(ifid, activePointCoords)
					caller.SetNthControlPointLocked(ifid, True)
			
			if 'bot' in activeLabel:
				oppositePoint = 'top'
				self.ui.botX.value = activePointCoords[0]
				self.ui.botY.value = activePointCoords[1]
				self.ui.botZ.value = activePointCoords[2]
			elif 'top' in activeLabel:
				oppositePoint = 'bot'
				self.ui.topX.value = activePointCoords[0]
				self.ui.topY.value = activePointCoords[1]
				self.ui.topZ.value = activePointCoords[2]

			oppositePointCoords = getPointCoords((self.ui.planName.currentText + '_line_post'), oppositePoint, node_type='vtkMRMLMarkupsLineNode')
			if np.array_equal(adjustPrecision(oppositePointCoords), adjustPrecision(np.array([0.0] * 3))):
				oppositePointCoords = getPointCoords(oppositePoint, oppositePoint)

			if not np.array_equal(adjustPrecision(oppositePointCoords), adjustPrecision(np.array([0.0] * 3))):
				self.convertFiducialNodesToLine(activeLabel, oppositePoint, self.ui.planName.currentText + '_line_post')

				botPointCoords = getPointCoords((self.ui.planName.currentText + '_line_post'), 'bot', node_type='vtkMRMLMarkupsLineNode')
				topPointCoords = getPointCoords((self.ui.planName.currentText + '_line_post'), 'top', node_type='vtkMRMLMarkupsLineNode')

				self.ui.botX.value = botPointCoords[0]
				self.ui.botY.value = botPointCoords[1]
				self.ui.botZ.value = botPointCoords[2]
				self.ui.topX.value = topPointCoords[0]
				self.ui.topY.value = topPointCoords[1]
				self.ui.topZ.value = topPointCoords[2]

	def onButtonClick(self, button):
		if 'LockButton' in button.name:
			fiducialPoint = button.name.replace('LockButton', '')
			pointLocked = True
			pointExists = False
			fiducialNode = getMarkupsNode(fiducialPoint)
			for ifid in range(fiducialNode.GetNumberOfControlPoints()):
				if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
					pointExists = True
				if fiducialNode.GetNthMarkupLocked(ifid) == 1 and pointExists:
					fiducialNode.SetNthControlPointLocked(ifid, False)
					pointLocked = False
					button.setStyleSheet('background-color: green')
					button.setText('Lock')
					fiducialNode.GetDisplayNode().SetVisibility(1)

			if not pointExists:
				warningBox(f"No fiducial defined for {fiducialPoint}, please set a point.")
				return
			if pointExists and pointLocked:
				button.setStyleSheet('')
				button.setText('Unlock')
				fiducialNode = getMarkupsNode(fiducialPoint)
				for ifid in range(fiducialNode.GetNumberOfControlPoints()):
					if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
						pointCoordsWorld = [0]*3
						fiducialNode.GetNthControlPointPositionWorld(ifid, pointCoordsWorld)
						fiducialNode.SetNthControlPointLocked(ifid, True)
						fiducialNode.SetNthControlPointVisibility(ifid, 1)

				if 'bot' in fiducialPoint:
					self.ui.botX.value = pointCoordsWorld[0]
					self.ui.botY.value = pointCoordsWorld[1]
					self.ui.botZ.value = pointCoordsWorld[2]
				elif 'top' in fiducialPoint:
					self.ui.topX.value = pointCoordsWorld[0]
					self.ui.topY.value = pointCoordsWorld[1]
					self.ui.topZ.value = pointCoordsWorld[2]

		elif 'JumpButton' in button.name:
			fiducialPoint = button.name.replace('JumpButton', '')
			fiducialNode = getMarkupsNode(fiducialPoint)
			for ifid in range(fiducialNode.GetNumberOfControlPoints()):
				if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
					slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(fiducialNode.GetID(), ifid)
					crossCoordsWorld = np.zeros(3)
					fiducialNode.GetNthControlPointPositionWorld(ifid, crossCoordsWorld)

			crossHairPlanningNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLCrosshairNode')
			crossHairPlanningNode.SetCrosshairRAS(vtk.vtkVector3d(crossCoordsWorld[0], crossCoordsWorld[1], crossCoordsWorld[2]))


	def onPostActualElecButtonGroupClicked(self, button):
		"""
		Slot for ``Plot Actual Lead:`` button group under ``Left Plan``
		
		:param button: id of the button clicked
		:type button: Integer
		"""
		if button == -2:
			self.postActualElecPlot = True
		if button == -3:
			self.postActualElecPlot = False

	def onPostActualMERTracksButtonClicked(self, button):
		"""
		Slot for ``Plot MER Tracks:`` button group under ``Left Plan``
		
		:param button: id of the button clicked
		:type button: Integer
		"""
		if button == -2:
			self.postActualMERTracksPlot = True
		if button == -3:
			self.postActualMERTracksPlot = False

	def convertFiducialNodesToLine(self, node1_name, node2_name, new_name, visibility=True):
		lineNode = getMarkupsNode(new_name, node_type='vtkMRMLMarkupsLineNode', create=True)
		#if slicer.util.getNode('acpc').GetParentTransformNode() is not None:
		#	lineNode.SetAndObserveTransformNodeID(slicer.util.getNode('acpc').GetParentTransformNode().GetID())
		for inode in [node1_name, node2_name]:
			node_temp = slicer.util.getNode(inode)
			if node_temp.GetNumberOfControlPoints() > 0:
				for ifid in range(node_temp.GetNumberOfControlPoints()):
					nodeCoords = [0]*3
					nodelabel = ''.join([lbl for lbl in node_temp.GetNthControlPointLabel(ifid) if lbl.isalpha()])
					node_temp.GetNthControlPointPositionWorld(ifid, nodeCoords)

				nodePresent = False
				for ifid in range(lineNode.GetNumberOfControlPoints()):
					if nodelabel in lineNode.GetNthControlPointLabel(ifid):
						lineNode.SetNthControlPointPositionWorld(ifid, nodeCoords[0], nodeCoords[1], nodeCoords[2])
						lineNode.SetNthControlPointLocked(ifid, True)
						nodePresent = True

				if not nodePresent:
					n = lineNode.AddControlPointWorld(vtk.vtkVector3d(nodeCoords[0], nodeCoords[1], nodeCoords[2]))
					lineNode.SetNthControlPointLabel(n, nodelabel)
					lineNode.SetNthControlPointLocked(n, True)
				node_temp.RemoveAllControlPoints()

		lineNode.GetDisplayNode().PointLabelsVisibilityOn()

		if not visibility:
			lineNode.GetDisplayNode().SetVisibility(0)

	def onActualElecPlotButton(self, button):
		"""
		Slot for ``Update Activity`` button 
		
		:param button: id of the button clicked (left/right side)
		:type button: Integer
		"""

		if sum(np.array([self.ui.topX.value, self.ui.topY.value, self.ui.topZ.value])) == 0:
			warningBox('Please choose entry point.')
			return

		if sum(np.array([self.ui.botX.value, self.ui.botY.value, self.ui.botZ.value])) == 0:
			warningBox('Please choose target point.')
			return

		if self.ui.postElecCB.currentText == 'Select Electrode':
			warningBox('Please choose an electrode model.')
			return

		plan_name = self.ui.planName.currentText
		origin_point = getPointCoords('acpc', 'mcp')
		target_coords_world = np.array([self.ui.botX.value, self.ui.botY.value, self.ui.botZ.value])
		entry_coords_world = np.array([self.ui.topX.value, self.ui.topY.value, self.ui.topZ.value])
		
		self.postElecModel = self.ui.postElecCB.currentText

		self.postMicroModel = self.ui.postElecCB.currentText if self.ui.postElecCB.currentText != 'None' else []

		children = self.ui.postTrajUsedGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked():
				self.implantTraj = i.text.lower()

		self.logic.plotData(button, plan_name, origin_point, target_coords_world, entry_coords_world, self.postElecModel, 
			self.postMicroModel, self.implantTraj, self.postActualElecPlot, self.postActualMERTracksPlot)
		


#
# postopLocalizationLogic
#

class postopLocalizationLogic(ScriptedLoadableModuleLogic):
	"""This class should implement all the actual
	computation done by your module.  The interface
	should be such that other python code can import
	this class and make use of the functionality without
	requiring an instance of the Widget.
	Uses ScriptedLoadableModuleLogic base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self):
		"""
		Called when the logic class is instantiated. Can be used for initializing member variables.
		"""
		ScriptedLoadableModuleLogic.__init__(self)

		self._parameterNode = None
		self.postopLocalizationInstance = None
		self.FrameAutoDetect = False

		self.leftChanIndex = {1:'anterior',  3:'posterior',  0:'medial',  2:'lateral'}
		self.rightChanIndex = {1:'anterior',  3:'posterior',  2:'medial',  0:'lateral'}
		self.left_new_center = {1:[3],  3:[1],  0:[2],  2:[0]}
		self.right_new_center = {1:[3],  3:[1],  2:[0],  0:[2]}

	def getParameterNode(self, replace=False):
		"""Get the postopLocalization parameter node.

		"""
		node = self._findParameterNodeInScene()
		if not node:
			node = self._createParameterNode()
		if replace:
			slicer.mrmlScene.RemoveNode(node)
			node = self._createParameterNode()
		return node

	def _findParameterNodeInScene(self):
		node = None
		for i in range(slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScriptedModuleNode")):
			if slicer.mrmlScene.GetNthNodeByClass(i, "vtkMRMLScriptedModuleNode").GetModuleName() == "trajectoryGuide":
				node = slicer.mrmlScene.GetNthNodeByClass(i, "vtkMRMLScriptedModuleNode")
				break
		return node

	def _createParameterNode(self):
		""" Create the postopLocalization parameter node.

		This is used internally by getParameterNode - shouldn't really
		be called for any other reason.

		"""
		node = slicer.vtkMRMLScriptedModuleNode()
		node.SetSingletonTag("trajectoryGuide")
		node.SetModuleName("trajectoryGuide")
		self.setDefaultParameters(node)
		slicer.mrmlScene.AddNode(node)
		# Since we are a singleton, the scene won't add our node into the scene,
		# but will instead insert a copy, so we find that and return it
		node = self._findParameterNodeInScene()
		return node

	def setDefaultParameters(self, parameterNode):
		"""
		Initialize parameter node with default settings.
		"""
		if getattr(sys, 'frozen', False):
			trajectoryGuidePath = os.path.dirname(os.path.dirname(sys.argv[0]))
		elif __file__:
			trajectoryGuidePath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

		if not parameterNode.GetParameter("trajectoryGuidePath"):
			parameterNode.SetParameter("trajectoryGuidePath", trajectoryGuidePath)
		if not parameterNode.GetParameter("trajectoryGuide_settings"):
			parameterNode.SetParameter("trajectoryGuide_settings", os.path.join(trajectoryGuidePath, 'resources', 'settings', 'trajectoryGuide_settings.json'))

	def setPatientSpecificParamters(self, parameterNode):
		for ipath in {'summaries','settings'}:
			if not os.path.exists(os.path.join(parameterNode.GetParameter('derivFolder'), ipath)):
				os.makedirs(os.path.join(parameterNode.GetParameter('derivFolder'), ipath))
				if 'settings' in ipath:
					shutil.copy2(
						os.path.join(parameterNode.GetParameter('trajectoryGuidePath'),'resources', 'settings', 'model_visibility.json'),
						os.path.join(parameterNode.GetParameter('derivFolder'), ipath, 'model_visibility.json')
					)
					shutil.copy2(
						os.path.join(parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'settings', 'model_color.json'),
						os.path.join(parameterNode.GetParameter('derivFolder'), ipath, 'model_color.json')
					)

	def addCustomLayouts(self):

		addCustomLayouts()
		slicer.app.layoutManager().setLayout(slicerLayout)

	def plotData(self, button, plan_name, origin_point, target_coords_world, entry_coords_world, postElecModel, postMicroModel, implantTraj, postActualElecPlot=True, postActualMERTracksPlot=True):
		"""
		Slot for ``Update Activity`` button 
		
		:param button: id of the button clicked (left/right side)
		:type button: Integer
		"""

		parameterNode = self.getParameterNode()
		surgical_info = os.path.join(parameterNode.GetParameter('derivFolder'), f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")
		with open(surgical_info) as (side_file):
			surgical_data = json.load(side_file)
		
		if plan_name not in list(surgical_data['trajectories']):
			surgical_data['trajectories'][plan_name] = {}
			surgical_data['trajectories'][plan_name]['plan_name'] = plan_name
			surgical_data['trajectories'][plan_name]['side'] = 'left' if target_coords_world[0] < origin_point[0] else 'right'
			
		if 'pre' not in list(surgical_data['trajectories'][plan_name]):
			surgical_data['trajectories'][plan_name]['pre']={}
			surgical_data['trajectories'][plan_name]['pre']['elecUsed'] = postElecModel
			surgical_data['trajectories'][plan_name]['pre']['microUsed'] = postMicroModel
			surgical_data['trajectories'][plan_name]['pre']['mer_tracks']={
				'center':{
					'mer_top':[],
					'mer_bot':[],
					'acpc_entry': [],
					'acpc_target': []
				}
			}
		else:
			if postElecModel not in surgical_data['trajectories'][plan_name]['pre']['elecUsed']: surgical_data['trajectories'][plan_name]['pre']['elecUsed']=postElecModel
			if postMicroModel not in surgical_data['trajectories'][plan_name]['pre']['microUsed']: surgical_data['trajectories'][plan_name]['pre']['microUsed']=postMicroModel

		mer_depths = {}
		lead_depth=0
		if 'intra' not in list(surgical_data['trajectories'][plan_name]):
			surgical_data['trajectories'][plan_name]['intra']={}
			surgical_data['trajectories'][plan_name]['intra']['lead_traj_chosen'] = implantTraj.lower()
			surgical_data['trajectories'][plan_name]['intra']['mer_tracks'] = {}
		else:
			if 'lead_depth' in list(surgical_data['trajectories'][plan_name]['intra']):
				lead_depth=surgical_data['trajectories'][plan_name]['intra']['lead_depth']
				if implantTraj.lower() !=surgical_data['trajectories'][plan_name]['intra']['lead_traj_chosen']: surgical_data['trajectories'][plan_name]['intra']['lead_traj_chosen']=implantTraj.lower()

				for ichan in list(surgical_data['trajectories'][plan_name]['intra']['mer_tracks']):
					mer_depths = {**mer_depths, **{
							ichan.lower(): [surgical_data['trajectories'][plan_name]['intra']['mer_tracks'][ichan]['mer_top'],
							surgical_data['trajectories'][plan_name]['intra']['mer_tracks'][ichan]['mer_bot']]
						}
					}
			else:
				surgical_data['trajectories'][plan_name]['intra']={}
				surgical_data['trajectories'][plan_name]['intra']['lead_traj_chosen'] = implantTraj.lower()
				surgical_data['trajectories'][plan_name]['intra']['mer_tracks'] = {}

		surgical_data['trajectories'][plan_name]['post'] = {
			'target':list(target_coords_world),
			'entry':list(entry_coords_world)
		}

		postElecModelTag = electrodeModels[postElecModel]['filename']

		mer_info={}
		mer_info['center']=mer_depths['center'] if 'center' in list(mer_depths) else ['n/a', 'n/a']
		mer_info['anterior']=mer_depths['anterior'] if 'anterior' in list(mer_depths) else ['n/a', 'n/a']
		mer_info['posterior']=mer_depths['posterior'] if 'posterior' in list(mer_depths) else ['n/a', 'n/a']
		mer_info['medial']=mer_depths['medial'] if 'medial' in list(mer_depths) else ['n/a', 'n/a']
		mer_info['lateral']=mer_depths['lateral'] if 'lateral' in list(mer_depths) else ['n/a', 'n/a']

		channel_index = self.leftChanIndex if surgical_data['trajectories'][plan_name]['side'] == 'left' else self.rightChanIndex
		channel_new_center=self.left_new_center if surgical_data['trajectories'][plan_name]['side'] == 'left' else self.right_new_center
		channels_used=list(surgical_data['trajectories'][plan_name]['pre']['mer_tracks'])

		with open(os.path.join(parameterNode.GetParameter('derivFolder'), 'settings', 'model_visibility.json')) as (settings_file):
			slice_vis = json.load(settings_file)
		
		with open(os.path.join(parameterNode.GetParameter('derivFolder'), 'settings', 'model_color.json')) as (settings_file):
			model_colors = json.load(settings_file)
		
		model_parameters = {
			'plan_name':plan_name,
			'type':'post',
			'side': surgical_data['trajectories'][plan_name]['side'],
			'elecUsed':postElecModel, 
			'microUsed': postMicroModel,
			'data_dir':parameterNode.GetParameter('derivFolder'),
			'lead_fileN':f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_task-{plan_name}_type-{postElecModelTag.lower()}_lead.vtk", 
			'contact_fileN':f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_task-{plan_name}_type-{postElecModelTag.lower()}_label-%s_contact.vtk", 
			'model_col':model_colors['actualLeadColor'], 
			'model_vis':slice_vis['actualLead3DVis'], 
			'contact_col':model_colors['actualContactColor'],
			'contact_vis':slice_vis['actualContact3DVis'],
			'plot_model':postActualElecPlot
		}
		
		plotLead(entry_coords_world.copy(),target_coords_world.copy(),origin_point.copy(), model_parameters)
		
		lineNode = getMarkupsNode(plan_name + '_line_post', 'vtkMRMLMarkupsLineNode', False)
		if lineNode is not None:
			slicer.mrmlScene.RemoveNode(slicer.util.getNode(lineNode.GetName()))

		markupsNodeTrackLine = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsLineNode')
		markupsNodeTrackLine.SetName(plan_name + '_line_post')
		markupsNodeTrackLine.GetDisplayNode().SetVisibility(0)
		markupsNodeTrackLine.AddDefaultStorageNode()

		point_label='Lentry' if entry_coords_world[0] < origin_point[0] else 'Rentry'
		n = markupsNodeTrackLine.AddControlPoint(vtk.vtkVector3d(entry_coords_world[0], entry_coords_world[1], entry_coords_world[2]))
		markupsNodeTrackLine.SetNthControlPointLabel(n, point_label)
		markupsNodeTrackLine.SetNthControlPointLocked(n, True)
		
		point_label='Ltarget' if target_coords_world[0] < origin_point[0] else 'Rtarget'
		n = markupsNodeTrackLine.AddControlPoint(vtk.vtkVector3d(target_coords_world[0], target_coords_world[1], target_coords_world[2]))
		markupsNodeTrackLine.SetNthControlPointLabel(n, point_label)
		markupsNodeTrackLine.SetNthControlPointLocked(n, True)

		DirVec = entry_coords_world - target_coords_world
		MagVec = np.sqrt([np.square(DirVec[0]) + np.square(DirVec[1]) + np.square(DirVec[2])])
		NormVec = np.array([float(DirVec[0] / MagVec), float(DirVec[1] / MagVec), float(DirVec[2] / MagVec)])
		
		
		alpha,beta=frame_angles(target_coords_world,entry_coords_world)
		alpha = float(90 - alpha)
		beta = beta-90

		R = rotation_matrix(alpha, beta, 0)
		t = 2 * np.pi * np.arange(0, 1, 0.25)
		
		coords_norm = 2 * np.c_[(np.cos(t), np.sin(t), np.zeros_like(t))].T
		new_coords_shift = (np.dot(R, coords_norm).T + target_coords_world).T
		
		if implantTraj.lower() == 'center':
			new_coords_shift_final = new_coords_shift
		else:
			chanIdx = channel_new_center.get(list(channel_index.keys())[[i for i, x in enumerate(channel_index.values()) if x.lower() == implantTraj.lower()][0]])[0]
			t = 2 * np.pi * np.arange(0, 1, 0.25)
			coords_shift = 2 * np.c_[(np.cos(t), np.sin(t), np.zeros_like(t))].T
			R = rotation_matrix(alpha, beta, 0)
			new_coords_shift_final = (np.dot(R, coords_shift).T + list(new_coords_shift.T[chanIdx])).T
				
		ch_info={}
		for ichan in channels_used:

			activity_filename = os.path.join(parameterNode.GetParameter('derivFolder'), 
				f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_task-{plan_name}_type-mer_label-{ichan}_activity.vtk")
			
			track_filename = os.path.join(parameterNode.GetParameter('derivFolder'), 
				f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_task-{plan_name}_type-mer_label-{ichan}_track")
			
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if os.path.basename(activity_filename).split('.vtk')[0] in imodel.GetName():
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetID()))
				elif os.path.basename(track_filename).split('.vtk')[0] in imodel.GetName():
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetID()))

			coords_track=None
			coords_activity=None
			if 'center' in ichan:
				P1_shift = new_coords_shift_final.T[2] - (new_coords_shift_final.T[2] - new_coords_shift_final.T[0]) / 2
				coords_track = np.hstack((P1_shift, P1_shift + NormVec.T * MagVec))
				
				if not 'n/a' in mer_info[ichan] and not all(v == 0.0 for v in mer_info[ichan]):
					mer_bot = mer_info[ichan][1]
					mer_top = mer_info[ichan][0]
					coords_activity = np.hstack((P1_shift + NormVec.T * (-1 * (mer_info['center'][0]-lead_depth)),P1_shift + NormVec.T * (-1 * (mer_info['center'][1]-lead_depth))))
				else:
					mer_bot = 'n/a'
					mer_top = 'n/a'

				ch_info_temp = {
					'mer_top':mer_top,
					'mer_bot':mer_bot,
					'acpc_entry':list(adjustPrecision(P1_shift + NormVec.T * MagVec)),
					'acpc_target':list(adjustPrecision(P1_shift))
				}
			else:
				for idx, chan in channel_index.items():
					if ichan == chan:
						coords_track = np.hstack((new_coords_shift_final.T[idx], new_coords_shift_final.T[idx] + NormVec.T * MagVec))

						if not 'n/a' in mer_info[ichan] and not all(v == 0.0 for v in mer_info[ichan]):
							mer_bot = mer_info[ichan][1]
							mer_top = mer_info[ichan][0]
							coords_activity = np.hstack((new_coords_shift_final.T[idx] + NormVec.T * (-1 * (mer_info[ichan][0]-lead_depth)),new_coords_shift_final.T[idx] + NormVec.T * (-1 * (mer_info[ichan][1]-lead_depth))))
						else:
							mer_bot = 'n/a'
							mer_top = 'n/a'

						ch_info_temp = {
							'mer_top':mer_top,
							'mer_bot':mer_bot,
							'acpc_entry':list(adjustPrecision(new_coords_shift_final.T[idx] + NormVec.T * MagVec)),
							'acpc_target':list(adjustPrecision(new_coords_shift_final.T[idx]))
						}

			if coords_track is not None and postActualMERTracksPlot:
				ch_info[ichan] = ch_info_temp

				model_parameters['mer_filename'] = track_filename
				model_parameters['model_col'] = model_colors['plannedMicroelectrodesColor']
				model_parameters['model_vis'] = model_colors['plannedMicroelectrodesColor']

				plotMicroelectrode(coords_track, alpha, beta, model_parameters)

				
			if coords_activity is not None:

				vtkModelBuilder = vtkModelBuilderClass()
				vtkModelBuilder.coords = coords_activity
				vtkModelBuilder.tube_radius = 0.3
				vtkModelBuilder.filename = activity_filename
				vtkModelBuilder.model_color = model_colors['actualMERActivityColor']
				vtkModelBuilder.model_visibility = slice_vis['actualMERActivity3DVis']
				vtkModelBuilder.build_cylinder()
				
				if postActualMERTracksPlot:
					vtkModelBuilder.add_to_scene()

		surgical_data['trajectories'][plan_name]['post']['mer_tracks']=ch_info
		
		json_output = json.dumps(surgical_data, indent=4)
		with open(surgical_info, 'w') as (fid):
			fid.write(json_output)
			fid.write('\n')

		volNode=None
		imageVolumes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
		for iimage in imageVolumes:
			if iimage.GetAttribute('refVol')=='1':
				volNode=iimage

		if volNode is None:
			layoutManager = slicer.app.layoutManager()
			volNode=slicer.util.getNode(layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode().GetBackgroundVolumeID())

		if not os.path.exists(os.path.join(parameterNode.GetParameter('derivFolder'), f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_coordsystem.json")):
			coordsystem_file_json = {}
			coordsystem_file_json['IntendedFor'] = os.path.join(parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
			coordsystem_file_json['FiducialsCoordinateSystem'] = 'RAS'
			coordsystem_file_json['FiducialsCoordinateUnits'] = 'mm'
			coordsystem_file_json['FiducialsCoordinateSystemDescription'] = "RAS orientation: Origin halfway between LPA and RPA, positive x-axis towards RPA, positive y-axis orthogonal to x-axis through Nasion,  z-axis orthogonal to xy-plane, pointing in superior direction."
			coordsystem_file_json['FiducialsCoordinates'] = {}
		else:
			with open(os.path.join(parameterNode.GetParameter('derivFolder'), f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_coordsystem.json")) as coordsystem_file:
				coordsystem_file_json = json.load(coordsystem_file)
		
		coordsystem_file_json['IntendedFor'] = os.path.join(parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
		coordsystem_file_json['FiducialsCoordinates']['entry']=adjustPrecision(entry_coords_world).tolist()
		coordsystem_file_json['FiducialsCoordinates']['target']=adjustPrecision(target_coords_world).tolist()
		coordsystem_file_json['FiducialsCoordinates']['origin_point']=adjustPrecision(origin_point).tolist()

		for ichan in list(surgical_data['trajectories'][plan_name]['post']['mer_tracks']):
			coordsystem_file_json['FiducialsCoordinates'][f"{plan_name}_{ichan}_entry"]=adjustPrecision(surgical_data['trajectories'][plan_name]['post']['mer_tracks'][ichan]['acpc_entry']).tolist()
			coordsystem_file_json['FiducialsCoordinates'][f"{plan_name}_{ichan}_target"]=adjustPrecision(surgical_data['trajectories'][plan_name]['post']['mer_tracks'][ichan]['acpc_target']).tolist()

		json_output = json.dumps(coordsystem_file_json, indent=4)
		with open(os.path.join(parameterNode.GetParameter('derivFolder'), f"{parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_coordsystem.json"), 'w') as fid:
			fid.write(json_output)
			fid.write('\n')



#
# postopLocalizationTest
#

class postopLocalizationTest(ScriptedLoadableModuleTest):
	"""
	This is the test case for your scripted module.
	Uses ScriptedLoadableModuleTest base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def setUp(self):
		""" Do whatever is needed to reset the state - typically a scene clear will be enough.
		"""
		slicer.mrmlScene.Clear()

	def runTest(self):
		"""Run as few or as many tests as needed here.
		"""
		self.setUp()
		self.test_postopLocalization1()

	def test_postopLocalization1(self):
		""" Ideally you should have several levels of tests.  At the lowest level
		tests should exercise the functionality of the logic with different inputs
		(both valid and invalid).  At higher levels your tests should emulate the
		way the user would interact with your code and confirm that it still works
		the way you intended.
		One of the most important features of the tests is that it should alert other
		developers when their changes will have an impact on the behavior of your
		module.  For example, if a developer removes a feature that you depend on,
		your test should break so they know that the feature is needed.
		"""

		self.delayDisplay("Starting the test")

		# Get/create input data

		import SampleData
		registerSampleData()
		inputVolume = SampleData.downloadSample('postopLocalization1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = postopLocalizationLogic()

		# Test algorithm with non-inverted threshold
		logic.process(inputVolume, outputVolume, threshold, True)
		outputScalarRange = outputVolume.GetImageData().GetScalarRange()
		self.assertEqual(outputScalarRange[0], inputScalarRange[0])
		self.assertEqual(outputScalarRange[1], threshold)

		# Test algorithm with inverted threshold
		logic.process(inputVolume, outputVolume, threshold, False)
		outputScalarRange = outputVolume.GetImageData().GetScalarRange()
		self.assertEqual(outputScalarRange[0], inputScalarRange[0])
		self.assertEqual(outputScalarRange[1], inputScalarRange[1])

		self.delayDisplay('Test passed')
