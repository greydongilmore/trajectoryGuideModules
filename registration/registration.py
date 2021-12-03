import os
import sys
import shutil
import numpy as np
import logging
import json
import glob
import stat
import vtk, qt, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import sys, subprocess

if getattr(sys, 'frozen', False):
	cwd = os.path.dirname(sys.argv[0])
elif __file__:
	cwd = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.dirname(cwd))

from helpers.helpers import warningBox, getReverseTransform, addCustomLayouts, CheckableComboBox
from helpers.variables import fontSetting, slicerLayout,groupboxStyle, groupboxStyleTitle, fontSettingTitle,ctkCollapsibleGroupBoxStyle,ctkCollapsibleGroupBoxTitle

#
# registration
#

class registration(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "03: Registration"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = []
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This module performs image registration, wrapping three registrations tool: NiftyReg, ANTS, and FSL.\n
For use details see <a href="https://trajectoryguide.greydongilmore.com/widgets/05_registration.html">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# registrationWidget
#

class registrationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
		self.layerReveal = None
		self.previousWindow=None
		self.previousLevel=None
		self.transformNodeFrameSpace=None
		self.frameVolumeName = None
		self.registrationInProgress = False
		self.frameVolume = []

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
		self.logic = registrationLogic()
		self.logic.logCallback = self.addLog

		# Connections
		self._setupConnections()

	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/registration.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)

		self.ui.referenceVolCBox.setMRMLScene(slicer.mrmlScene)
		self.ui.referenceVolCBox.addAttribute('vtkMRMLScalarVolumeNode', 'regVol', '1')
		self.ui.frameVolCBox.setMRMLScene(slicer.mrmlScene)
		self.ui.frameVolCBox.addAttribute('vtkMRMLScalarVolumeNode', 'frameVol', '1')
		self.ui.referenceVolTemplateCBox.setMRMLScene(slicer.mrmlScene)
		self.ui.referenceVolTemplateCBox.addAttribute('vtkMRMLScalarVolumeNode', 'regVol', '1')

		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
		
		self.regFloatingCB = CheckableComboBox()
		self.regFloatingCB.setFont(qt.QFont('Arial', 11))
		self.regFloatingCB.setFixedWidth(340)

		self.floatVolLabel=qt.QLabel('Floating Volumes:')
		self.floatVolLabel.setFixedWidth(120)
		self.floatVolLabel.setFont(qt.QFont('Arial', 11))
		self.floatVolLabel.setAlignment(qt.Qt.AlignLeft)

		self.ui.patientSpaceGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.templateSpaceGB.setStyleSheet(ctkCollapsibleGroupBoxStyle + f"color: {self.text_color}" + '}' + ctkCollapsibleGroupBoxTitle + f"color: {self.text_color}" + '}')
		self.ui.templateSpaceGB.collapsed = 1

		self.gridLayoutReg = self.uiWidget.findChild(qt.QWidget,'regFloatVolWig').layout()

		self.gridLayoutReg.addWidget(self.floatVolLabel,0,0)
		self.gridLayoutReg.addWidget(self.regFloatingCB,1,0)

		self.ui.regAlgorithmGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.niftyRegParametersGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.fslParametersGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.antsParametersGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.niftyRegAlgo.setStyleSheet(f"{fontSetting}margins: 12px;padding: 3px;")
		self.ui.flirtRegAlgo.setStyleSheet(f"{fontSetting}margins: 12px;padding: 3px;")
		self.ui.antsRegAlgo.setStyleSheet(f"{fontSetting}margins: 12px;padding: 3px;")

		#self.ui.regaladinInterpCB.addItems(['0 - NN', '1 - LIN', '3 - CUB', '4 - SINC'])
		#self.ui.regaladinInterpCB.setCurrentIndex(self.ui.regaladinInterpCB.findText('3 - CUB'))
		#self.ui.flirtCostCB.addItems(['mutualinfo', 'corratio', 'normcorr', 'normmi', 'leastsq', 'labeldiff', 'bbr'])
		#self.ui.flirtCostCB.setCurrentIndex(self.ui.flirtCostCB.findText('mutualinfo'))
		#self.ui.flirtSearchCostCB.addItems(['mutualinfo', 'corratio', 'normcorr', 'normmi', 'leastsq', 'labeldiff', 'bbr'])
		#self.ui.flirtSearchCostCB.setCurrentIndex(self.ui.flirtSearchCostCB.findText('mutualinfo'))
		#self.ui.flirtInterpCB.addItems(['trilinear', 'nearestneighbour', 'sinc', 'spline'])
		#self.ui.flirtInterpCB.setCurrentIndex(self.ui.flirtInterpCB.findText('spline'))
		
		
		#self.ui.antsQuickInterpCB.addItems(['Linear', 'NearestNeighbor', 'BSpline', 'GenericLabel'])
		#self.ui.antsQuickInterpCB.setCurrentIndex(self.ui.antsQuickInterpCB.findText('NearestNeighbor'))
		#self.ui.antsQuickTransformTypeCB.addItems(['rigid', 'rigid+affine'])
		#self.ui.antsQuickTransformTypeCB.setCurrentIndex(self.ui.antsQuickTransformTypeCB.findText('rigid'))

		#self.ui.antsInterpCB.addItems(['Linear', 'NearestNeighbor', 'BSpline', 'GenericLabel'])
		#self.ui.antsInterpCB.setCurrentIndex(self.ui.antsInterpCB.findText('BSpline'))
		#self.ui.antsMetricCB.addItems(['CC', 'MI', 'GC'])
		#self.ui.antsMetricCB.setCurrentIndex(self.ui.antsMetricCB.findText('CC'))
		
		self.ui.fslParametersGB.collapsed = 1
		self.ui.antsParametersGB.collapsed = 1
		self.ui.antsQuickParametersGB.collapsed = 1

		self.ui.regAlgorithmTemplateGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.niftyRegParametersTemplateGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.fslParametersTemplateGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.antsParametersTemplateGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.niftyRegAlgoTemplate.setStyleSheet(f"{fontSetting}margins: 12px;padding: 3px;")
		self.ui.flirtRegAlgoTemplate.setStyleSheet(f"{fontSetting}margins: 12px;padding: 3px;")
		self.ui.antsRegAlgoTemplate.setStyleSheet(f"{fontSetting}margins: 12px;padding: 3px;")

		#self.ui.antsQuickInterpTemplateCB.addItems(['Linear', 'NearestNeighbor', 'BSpline', 'GenericLabel'])
		#self.ui.antsQuickInterpTemplateCB.setCurrentIndex(self.ui.antsQuickInterpTemplateCB.findText('BSpline'))
		#self.ui.regaladinInterpTemplateCB.addItems(['0 - NN', '1 - LIN', '3 - CUB', '4 - SINC'])
		#self.ui.regaladinInterpTemplateCB.setCurrentIndex(self.ui.regaladinInterpCB.findText('3 - CUB'))
		#self.ui.flirtCostTemplateCB.addItems(['mutualinfo', 'corratio', 'normcorr', 'normmi', 'leastsq', 'labeldiff', 'bbr'])
		#self.ui.flirtCostTemplateCB.setCurrentIndex(self.ui.flirtCostTemplateCB.findText('mutualinfo'))
		#self.ui.flirtSearchCostTemplateCB.addItems(['mutualinfo', 'corratio', 'normcorr', 'normmi', 'leastsq', 'labeldiff', 'bbr'])
		#self.ui.flirtSearchCostTemplateCB.setCurrentIndex(self.ui.flirtSearchCostTemplateCB.findText('mutualinfo'))
		#self.ui.flirtInterpTemplateCB.addItems(['trilinear', 'nearestneighbour', 'sinc', 'spline'])
		#self.ui.flirtInterpTemplateCB.setCurrentIndex(self.ui.flirtInterpTemplateCB.findText('spline'))
		#self.ui.antsInterpTemplateCB.addItems(['Linear', 'NearestNeighbor', 'BSpline', 'GenericLabel'])
		#self.ui.antsInterpTemplateCB.setCurrentIndex(self.ui.antsInterpTemplateCB.findText('BSpline'))
		#self.ui.antsMetricTemplateCB.addItems(['CC', 'MI', 'GC'])
		#self.ui.antsMetricTemplateCB.setCurrentIndex(self.ui.antsMetricTemplateCB.findText('CC'))
		#self.ui.transformTypeTemplateCB.addItems(['rigid', 'rigid+affine', 'rigid+affine+syn', 'rigid+syn', 'rigid+affine+b-spl syn', 'rigid+b-spl syn'])
		#self.ui.transformTypeTemplateCB.setCurrentIndex(self.ui.transformTypeTemplateCB.findText('rigid+affine+syn'))

		self.ui.fslParametersTemplateGB.collapsed = 1
		self.ui.antsParametersTemplateGB.collapsed = 1
		self.ui.antsSynParametersTemplateGB.collapsed = 1
		
	def _setupConnections(self):

		# Make sure parameter node is initialized (needed for module reload)
		self.initializeParameterNode()

		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

		self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeAddedEvent, self.onScalerVolumeNodeAdded)
		self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeAboutToBeRemovedEvent, self.onScalerVolumeNodeRemoved)

		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		
		self.ui.regAlgoBG.buttonClicked.connect(self.onButtonClick)
		self.ui.regAlgoTemplateBG.buttonClicked.connect(self.onButtonClick)
		self.ui.referenceVolCBox.connect('currentNodeChanged(bool)', self.onReferenceVolCBox)
		self.ui.runRegistrationButton.connect('clicked(bool)', self.onRunRegistrationButton)
		self.ui.confrimRegistration.connect('clicked(bool)', self.onConfirmRegistration)
		self.ui.declineRegistration.connect('clicked(bool)', self.onDeclineRegistration)
		self.ui.compareVolumesButton.connect('clicked(bool)', self.onCompareVolumes)
		self.ui.layerRevealCheckBox.connect('toggled(bool)', self.onlayerRevealCheckBox)

		templateSpaces = [x.split('tpl-')[(-1)] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space')) if os.path.isdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', x))]
		self.ui.templateSpaceCB.addItems(['None']+templateSpaces)
		self.ui.templateSpaceCB.setCurrentIndex(self.ui.templateSpaceCB.findText('None'))

		buttonIconSize=qt.QSize(36, 36)
	
		self.ui.compareVolumesButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'registration', 'Resources', 'Icons', 'compare_light.png')))
		self.ui.compareVolumesButton.setIconSize(buttonIconSize)

		self.logic._addCustomLayouts()

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

	@vtk.calldata_type(vtk.VTK_OBJECT)
	def onScalerVolumeNodeAdded(self, caller, event, calldata):
		node = calldata
		if isinstance(node, slicer.vtkMRMLScalarVolumeNode) and 'coreg' not in node.GetName():
			file_sidecar=None
			if self._parameterNode.GetParameter('derivFolder'):
				if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), node.GetName() + '.json')):
					with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), node.GetName() + '.json')) as (file):
						file_sidecar = json.load(file)
				elif os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'),'frame', node.GetName() + '.json')):
					with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame',node.GetName() + '.json')) as (file):
						file_sidecar = json.load(file)
				
				if file_sidecar is not None:
					if np.all([not file_sidecar['coregistered'], file_sidecar['vol_type'] != 'reference']):
						self.regFloatingCB.addItem(node.GetName())
						index = self.regFloatingCB.findText(node.GetName(), qt.Qt.MatchFixedString)
						item = self.regFloatingCB.model().item(index, 0)
						item.setCheckState(qt.Qt.Checked)
			else:
				self.regFloatingCB.addItem(node.GetName())
				index = self.regFloatingCB.findText(node.GetName(), qt.Qt.MatchFixedString)
				item = self.regFloatingCB.model().item(index, 0)
				item.setCheckState(qt.Qt.Checked)

	@vtk.calldata_type(vtk.VTK_OBJECT)
	def onScalerVolumeNodeRemoved(self, caller, event, calldata):
		node = calldata
		if isinstance(node, slicer.vtkMRMLScalarVolumeNode):

			if node.GetName() != '':
				
				index = self.regFloatingCB.findText(node.GetName(), qt.Qt.MatchFixedString)
				if index is not None:
					self.regFloatingCB.removeItem(index)

	def onButtonClick(self, button):
		if 'nifty' in button.name:
			if 'Template' in button.name:
				self.ui.niftyRegParametersTemplateGB.collapsed = 0
				self.ui.fslParametersTemplateGB.collapsed = 1
				self.ui.antsParametersTemplateGB.collapsed = 1
				self.ui.antsSynParametersTemplateGB.collapsed = 1
			else:
				self.ui.niftyRegParametersGB.collapsed = 0
				self.ui.fslParametersGB.collapsed = 1
				self.ui.antsParametersGB.collapsed = 1
				self.ui.antsQuickParametersGB.collapsed = 1
		elif 'flirt' in button.name:
			if 'Template' in button.name:
				self.ui.niftyRegParametersTemplateGB.collapsed = 1
				self.ui.fslParametersTemplateGB.collapsed = 0
				self.ui.antsParametersTemplateGB.collapsed = 1
				self.ui.antsSynParametersTemplateGB.collapsed = 1
			else:
				self.ui.niftyRegParametersGB.collapsed = 1
				self.ui.fslParametersGB.collapsed = 0
				self.ui.antsParametersGB.collapsed = 1
				self.ui.antsQuickParametersGB.collapsed = 1
		elif 'antsReg' in button.name:
			if 'Template' in button.name:
				self.ui.niftyRegParametersTemplateGB.collapsed = 1
				self.ui.fslParametersTemplateGB.collapsed = 1
				self.ui.antsParametersTemplateGB.collapsed = 0
				self.ui.antsSynParametersTemplateGB.collapsed = 1
			else:
				self.ui.niftyRegParametersGB.collapsed = 1
				self.ui.fslParametersGB.collapsed = 1
				self.ui.antsParametersGB.collapsed = 0
				self.ui.antsQuickParametersGB.collapsed = 1
		elif 'antsQuickReg' in button.name:
			if 'Template' in button.name:
				self.ui.niftyRegParametersTemplateGB.collapsed = 1
				self.ui.fslParametersTemplateGB.collapsed = 1
				self.ui.antsParametersTemplateGB.collapsed = 1
				self.ui.antsSynParametersTemplateGB.collapsed = 0
			else:
				self.ui.niftyRegParametersGB.collapsed = 1
				self.ui.fslParametersGB.collapsed = 1
				self.ui.antsParametersGB.collapsed = 1
				self.ui.antsQuickParametersGB.collapsed = 0

	def onCompareVolumes(self):
		if self.ui.referenceComboBox.currentText == '':
			warningBox('No reference volume is present to use as background for comparison.')
			return
		if self.ui.floatingComboBox.currentText == '':
			warningBox('No floating volume is present to use as foreground for comparison.')
			return

		logic = CompareVolumesLogic()
		logic.firstCompare = self.firstCompare
		if f"space-{self.regAlgo['templateSpace']}_desc-affine" in self.ui.floatingComboBox.currentText:
			loadedOutputVolumeNode=None
			for ifile in [x for x in glob.glob(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'space','*')) if not os.path.isdir(x)]:
				if any(ifile.endswith(x) for x in {'.nii','.nii.gz'}) and self.regAlgo['templateSpace'] in os.path.split(ifile)[-1]:
					loadedOutputVolumeNode = slicer.util.loadVolume(ifile)

			if loadedOutputVolumeNode is not None:
				#templateTransform = list(slicer.util.getNodes(f"*from-subject_to-{self.regAlgo['templateSpace']}_xfm*").values())[0]
				#loadedOutputVolumeNode.SetAndObserveTransformNodeID(templateTransform.GetID())

				logic.viewersPerVolume(
					background=(loadedOutputVolumeNode),
					volumeNodes=[slicer.util.getNode(self.ui.floatingComboBox.currentText)]
				)
		else:
			logic.viewersPerVolume(
				background=(slicer.util.getNode(self.ui.referenceComboBox.currentText)),
				volumeNodes=[slicer.util.getNode(self.ui.floatingComboBox.currentText)]
			)

		sliceCompositeNodes = slicer.util.getNodesByClass('vtkMRMLSliceCompositeNode')
		if any([x for x in sliceCompositeNodes if not x.GetLinkedControl()]):
			for sliceCompositeNode in sliceCompositeNodes:
				sliceCompositeNode.SetLinkedControl(True)

		self.previousWindow=None
		self.previousLevel=None
		img_data_kji = slicer.util.arrayFromVolume(slicer.util.getNode(self.ui.floatingComboBox.currentText))
		if img_data_kji.min() <-500:
			self.previousLevel = slicer.util.getNode(self.ui.floatingComboBox.currentText).GetDisplayNode().GetLevel()
			self.previousWindow = slicer.util.getNode(self.ui.floatingComboBox.currentText).GetDisplayNode().GetWindow()

			slicer.util.getNode(self.ui.floatingComboBox.currentText).GetDisplayNode().AutoWindowLevelOff()
			slicer.util.getNode(self.ui.floatingComboBox.currentText).GetDisplayNode().SetWindow(80)
			slicer.util.getNode(self.ui.floatingComboBox.currentText).GetDisplayNode().SetLevel(40)

	def onlayerRevealCheckBox(self):
		if self.layerReveal is not None:
			self.layerReveal.cleanup()
			self.layerReveal = None
		if self.ui.layerRevealCheckBox.checked:
			self.layerReveal = LayerReveal()

	def cleanup(self):
		if self.layerReveal:
			self.layerReveal.cleanup()


	def cleanUpPost(self):

		if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_transform_items.json")):
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_transform_items.json")) as (transform_file):
				transform_data = json.load(transform_file)
		else:
			transform_data={}

		if self.transformNodeFrameSpace is None and len(list(transform_data)) > 0:
			if len(slicer.util.getNodes(list(transform_data)[0])) > 0:
				self.transformNodeFrameSpace=list(slicer.util.getNodes(list(transform_data)[0]).values())[0]
		
		if self.transformNodeFrameSpace is not None:

			transform_data_current=[]
			if not self.transformNodeFrameSpace.GetName().endswith('_reverse'):
				self.transformNodeFrameSpace=getReverseTransform(self.transformNodeFrameSpace, True)
			
			imageVolumes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
			for iimage in imageVolumes:
				if f"space-{self.ui.referenceComboBox.currentText.split('_')[-1]}" in iimage.GetName():
					if iimage.GetParentTransformNode() is None:
						iimage.SetAttribute('refVol', '0')
						iimage.SetAndObserveTransformNodeID(self.transformNodeFrameSpace.GetID())
						transform_data_current.append(iimage.GetName())

			if self.referenceVolume is not None:
				if self.referenceVolume.GetParentTransformNode() is None:
					if len(list(transform_data)) > 0:
						if self.transformNodeFrameSpace.GetName() in list(transform_data):
							if not self.referenceVolume.GetName() in list(transform_data[self.transformNodeFrameSpace.GetName()]):
								self.referenceVolume.SetAndObserveTransformNodeID(self.transformNodeFrameSpace.GetID())
								transform_data_current.append(self.referenceVolume.GetName())
					else:
						if not self.referenceVolume.GetName() in transform_data_current:
								self.referenceVolume.SetAndObserveTransformNodeID(self.transformNodeFrameSpace.GetID())
								transform_data_current.append(self.referenceVolume.GetName())
			
			#markupNodes = slicer.util.getNodesByClass('vtkMRMLMarkupsFiducialNode')
			#for ifid in markupNodes:
			#	if ifid.GetName() in ('acpc','midline'):
			#		if ifid.GetNumberOfControlPoints() > 0:
			#			ifid.SetAndObserveTransformNodeID(self.transformNodeFrameSpace.GetID())
			#			transform_data_current.append(ifid.GetName())
#
#			#markupLineNode = slicer.util.getNodesByClass('vtkMRMLMarkupsLineNode')
#			#for ifid in markupLineNode:
#			#	if ifid.GetNumberOfControlPoints() > 0:
#			#		ifid.SetAndObserveTransformNodeID(self.transformNodeFrameSpace.GetID())
#			#		transform_data_current.append(ifid.GetName())
#
#			##models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
#			#for imodel in models:
#			#	if any(imodel.GetName().endswith(x) for x in ('_contact','_track','_lead','_vta','_activity')):
#			#		imodel.SetAndObserveTransformNodeID(self.transformNodeFrameSpace.GetID())
			#		transform_data_current.append(imodel.GetName())

			if transform_data_current:
				if self.transformNodeFrameSpace.GetName() in list(transform_data):
					transform_data[self.transformNodeFrameSpace.GetName()] = transform_data[self.transformNodeFrameSpace.GetName()] + transform_data_current
				else:
					transform_data[self.transformNodeFrameSpace.GetName()]=transform_data_current
				
				json_output = json.dumps(transform_data, indent=4)
				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_transform_items.json"), 'w') as (fid):
					fid.write(json_output)
					fid.write('\n')


		shutil.rmtree(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'temp'))
		
		orientations = {
			'Red':'Axial', 
			'Yellow':'Sagittal', 
			'Green':'Coronal'
		}

		layoutManager = slicer.app.layoutManager()
		for sliceViewName in layoutManager.sliceViewNames():
			layoutManager.sliceWidget(sliceViewName).mrmlSliceCompositeNode().SetForegroundOpacity(0)
			layoutManager.sliceWidget(sliceViewName).mrmlSliceCompositeNode().SetBackgroundVolumeID(slicer.util.getNode(self.ui.referenceComboBox.currentText).GetID())
			layoutManager.sliceWidget(sliceViewName).mrmlSliceCompositeNode().SetForegroundVolumeID(None)
			layoutManager.sliceWidget(sliceViewName).fitSliceToBackground()
			layoutManager.sliceWidget(sliceViewName).sliceController().children()[3].findChildren('ctkExpandButton')[0].setChecked(False)
			layoutManager.sliceWidget(sliceViewName).sliceController().barWidget().children()[1].setChecked(False)
			layoutManager.sliceWidget(sliceViewName).mrmlSliceNode().SetOrientation(orientations[sliceViewName])

		layoutManager.setLayout(slicerLayout)
		
		
		self.ui.referenceComboBox.clear()
		self.ui.templateSpaceCB.setCurrentIndex(self.ui.templateSpaceCB.findText('None'))
		
		if self.referenceVolume is not None:
			nodeName = os.path.basename(self.referenceVolume.GetStorageNode().GetFileName()).split('.nii')[0]
			alignFname = os.path.join(self._parameterNode.GetParameter('derivFolder'), nodeName + '.nii.gz')
			self.referenceVolume.SetAttribute('frameVol', '0')
			self.referenceVolume.SetAttribute('regVol', '1')
			slicer.util.saveNode(self.referenceVolume, alignFname, {'useCompression': False})

			slicer.mrmlScene.AddNode(self.referenceVolume)

		sliceCompositeNodes = slicer.util.getNodesByClass('vtkMRMLSliceCompositeNode')
		if not any([x for x in sliceCompositeNodes if not x.GetLinkedControl()]):
			for sliceCompositeNode in sliceCompositeNodes:
				sliceCompositeNode.SetLinkedControl(False)

		slicer.util.resetSliceViews()

	def onDeclineRegistration(self):
		declineModelName = self.ui.floatingComboBox.currentText if not self.ui.floatingComboBox.currentText[-1].isdigit() else self.ui.floatingComboBox.currentText[:-2]

		if f"{self.regAlgo['templateSpace']}_" in declineModelName:
			templateVolume=list(slicer.util.getNodes(f"*tpl-{self.regAlgo['templateSpace']}_*").values())
			for itemplate in templateVolume:
				final_nii = os.path.join(self._parameterNode.GetParameter('derivFolder'), 'space', itemplate.GetName())
				if os.path.exists(final_nii+'.nii.gz'):
					os.remove(final_nii+'.nii.gz')
				if os.path.exists(final_nii+'.json'):
					os.remove(final_nii+'.json')
				slicer.mrmlScene.RemoveNode(itemplate)

			transformNode = slicer.mrmlScene.GetFirstNodeByName(f"{os.path.basename(self._parameterNode.GetParameter('derivFolder')).replace(' ', '_')}_"+
				f"desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm")
		else:
			if 'acq-' in declineModelName.replace('_coreg', '').lower():
				acq_str=[x for x in declineModelName.replace('_coreg', '').split('_') if 'acq' in x][0]
				if 'frame' in acq_str.lower():
					transformName=declineModelName.replace('_coreg', '').split('_')[-1]+acq_str.split('-')[-1]
				else:
					transformName=acq_str.split('-')[-1]+declineModelName.replace('_coreg', '').split('_')[-1]
			else:
				transformName=declineModelName.replace('_coreg', '').split('_')[-1]

			transformNode = slicer.mrmlScene.GetFirstNodeByName(f"{os.path.basename(self._parameterNode.GetParameter('derivFolder')).replace(' ', '_')}_"+
				f"desc-rigid_from-{transformName}_to-{self.ui.referenceComboBox.currentText.split('_')[-1]}_xfm")

		if self.previousWindow is not None and self.previousLevel is not None:
			slicer.util.getNode(declineModelName).GetDisplayNode().AutoWindowLevelOff()
			slicer.util.getNode(declineModelName).GetDisplayNode().SetWindow(self.previousWindow)
			slicer.util.getNode(declineModelName).GetDisplayNode().SetLevel(self.previousLevel)

		self.ui.floatingComboBox.removeItem(self.ui.floatingComboBox.findText(declineModelName))
		slicer.mrmlScene.RemoveNode(slicer.util.getNode(declineModelName))
		os.remove(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'temp', declineModelName + '.nii.gz'))
		slicer.mrmlScene.RemoveNode(transformNode)

		if self.ui.floatingComboBox.count == 0:
			self.cleanUpPost()
		else:
			self.onCompareVolumes()

	def onConfirmRegistration(self):
		"""
		Slot for ``Delete Highlighted Volumes`` button

		"""

		slicer.app.setOverrideCursor(qt.Qt.WaitCursor)

		self.firstCompare = False
		coreg_node_name = self.ui.floatingComboBox.currentText
		original_node_name = coreg_node_name.replace('_coreg','')

		if f"space-{self.regAlgo['templateSpace']}_desc-affine" in coreg_node_name:
			templateVolume=list(slicer.util.getNodes(f"*tpl-{self.regAlgo['templateSpace']}_*").values())
			for itemplate in templateVolume:
				slicer.mrmlScene.RemoveNode(itemplate)

			self.ui.floatingComboBox.removeItem(self.ui.floatingComboBox.findText(coreg_node_name))
			outputVolumeNode = slicer.util.getNode(coreg_node_name)
			final_nii = os.path.join(self._parameterNode.GetParameter('derivFolder'), 'space', coreg_node_name + '.nii.gz')
			transformNodeFilename = os.path.join(self._parameterNode.GetParameter('derivFolder'),'space', f"{os.path.basename(self._parameterNode.GetParameter('derivFolder')).replace(' ', '_')}_"+
					f"desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm.h5")
			slicer.util.saveNode(outputVolumeNode, final_nii, {'useCompression': False})
			transformNode = slicer.mrmlScene.GetFirstNodeByName(f"{os.path.basename(self._parameterNode.GetParameter('derivFolder')).replace(' ', '_')}_"+
				f"desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm")
			slicer.util.saveNode(transformNode, transformNodeFilename, {'useCompression': False})

			shutil.copy2(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'temp', coreg_node_name + '.json'), os.path.join(self._parameterNode.GetParameter('derivFolder'), 'space', coreg_node_name + '.json'))

			slicer.mrmlScene.RemoveNode(outputVolumeNode)
			slicer.mrmlScene.RemoveNode(transformNode)
			slicer.util.resetSliceViews()
		else:
			self.ui.floatingComboBox.removeItem(self.ui.floatingComboBox.findText(coreg_node_name))
			files = [x for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'))) if any(x.endswith(y) for y in {'.nii', '.nii.gz'})]
			file_sidecar = []
			for f in files:
				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + '.json')) as (file):
					filenames = json.load(file)
				if filenames['node_name'] == original_node_name:
					file_sidecar = filenames
					break

			if file_sidecar:
				os.chmod(os.path.join(self._parameterNode.GetParameter('derivFolder'), file_sidecar['file_name']), stat.S_IRWXU)
				os.remove(os.path.join(self._parameterNode.GetParameter('derivFolder'), file_sidecar['file_name']))
				os.remove(os.path.join(self._parameterNode.GetParameter('derivFolder'), file_sidecar['file_name'].split('.nii')[0] + '.json'))
			else:
				files = [x for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'),'frame')) if any(x.endswith(y) for y in {'.nii', '.nii.gz'})]
				file_sidecar = []
				for f in files:
					with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame',f.split('.nii')[0] + '.json')) as (file):
						filenames = json.load(file)
					if filenames['node_name'] == original_node_name:
						file_sidecar = filenames
						break

			filenameParts=file_sidecar['file_name'].split('.nii')[0].split('_')
			filenameParts = [x for x in filenameParts if not any(y in x for y in ('space','desc'))]
			filenameFinal='_'.join([filenameParts[0],f"space-{self.ui.referenceComboBox.currentText.split('_')[-1]}"] + filenameParts[1:])

			frameVolume=False
			if 'acq-' in filenameFinal.lower():
				acq_str=[x for x in filenameFinal.split('_') if 'acq' in x][0]
				if 'frame' in acq_str.lower():
					frameVolume=True
					transformName=filenameFinal.split('_')[-1]+acq_str.split('-')[-1]
				else:
					transformName=acq_str.split('-')[-1]+filenameFinal.split('_')[-1]
			else:
				transformName=filenameFinal.split('_')[-1]

			outputVolumeNode = slicer.util.getNode(coreg_node_name)

			
			final_json = os.path.join(self._parameterNode.GetParameter('derivFolder'), filenameFinal + '.json')
			final_nii = os.path.join(self._parameterNode.GetParameter('derivFolder'), filenameFinal + '.nii.gz')
		
			file_sidecar['file_name'] = os.path.basename(final_nii)
			file_sidecar['node_name'] = filenameFinal

			slicer.util.saveNode(outputVolumeNode, final_nii, {'useCompression': False})
			slicer.mrmlScene.RemoveNode(outputVolumeNode)
			slicer.mrmlScene.RemoveNode(slicer.util.getNode(original_node_name))
			loadedOutputVolumeNode = slicer.util.loadVolume(final_nii)

			file_sidecar['coregistered'] = True
			file_sidecar['vol_type'] = 'moving' if file_sidecar['vol_type'] != 'frame' else file_sidecar['vol_type']
			file_sidecar['reference'] = self.ui.referenceComboBox.currentText
			file_sidecar['registration']={
				'algorithm':self.regAlgo['regAlgo'],
				'type':'linear',
				'parameters':self.regAlgo['parameters']
			}

			json_output = json.dumps(file_sidecar, indent=4)
			with open(final_json, 'w') as (fid):
				fid.write(json_output)
				fid.write('\n')

			transformNode = slicer.mrmlScene.GetFirstNodeByName(f"{os.path.basename(self._parameterNode.GetParameter('derivFolder')).replace(' ', '_')}_"+
				f"desc-rigid_from-{transformName}_to-{self.ui.referenceComboBox.currentText.split('_')[-1]}_xfm")
			
			if transformNode is not None:
				transformNodeFilename = os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{os.path.basename(self._parameterNode.GetParameter('derivFolder')).replace(' ', '_')}_"+
					f"desc-rigid_from-{transformName}_to-{self.ui.referenceComboBox.currentText.split('_')[-1]}_xfm.h5")
				
				slicer.util.saveNode(transformNode, transformNodeFilename, {'useCompression': False})
				if self.frameVolumeName is not None:
					frameVolumeName=[x for x in self.frameVolumeName.split('_') if not any(y in x for y in ('space','desc','coreg'))]
					if '_'.join(frameVolumeName[1:]) not in filenameFinal:
						slicer.mrmlScene.RemoveNode(transformNode)
					else:
						self.transformNodeFrameSpace=transformNode
				else:
					slicer.mrmlScene.RemoveNode(transformNode)

		

		if self.ui.floatingComboBox.count == 0:
			self.cleanUpPost()
			slicer.app.restoreOverrideCursor()
		else:
			slicer.app.restoreOverrideCursor()
			self.onCompareVolumes()

	def onReferenceVolCBox(self):
		"""
		Slot for ``Reference Volume:`` combo box
		
		"""
		if self.ui.referenceVolCBox.currentNode() is not None:
			self.referenceVolume = self.ui.referenceVolCBox.currentNode()
			self.referenceVolume.SetAttribute('frameVol', '0')
			self.referenceVolume.SetAttribute('regVol', '1')
			[self.ui.referenceVolCBox.nodeFromIndex(i).SetAttribute('frameVol', '1') for i in range(self.ui.referenceVolCBox.nodeCount()) if self.ui.referenceVolCBox.nodeFromIndex(i).GetName() != self.referenceVolume.GetName()]

			floatingVols = [self.ui.referenceVolCBox.nodeFromIndex(i).GetName() for i in range(self.ui.referenceVolCBox.nodeCount()) 
				if self.ui.referenceVolCBox.nodeFromIndex(i).GetName() != self.referenceVolume.GetName() and 
				self.ui.referenceVolCBox.nodeFromIndex(i).GetAttribute('coreg') != '1']
			
			self.ui.referenceVolTemplateCBox.setCurrentNode(self.referenceVolume)

			index = self.regFloatingCB.findText(self.referenceVolume.GetName(), qt.Qt.MatchFixedString)
			if index is not None:
				self.regFloatingCB.removeItem(index)

			AllItems = [self.regFloatingCB.itemText(i) for i in range(self.regFloatingCB.count)]
			
			for ifloat in floatingVols:
				if ifloat not in AllItems and not ifloat.startswith('r'):
					self.regFloatingCB.addItem(ifloat)
					index = self.regFloatingCB.findText(ifloat, qt.Qt.MatchFixedString)
					item = self.regFloatingCB.model().item(index, 0)
					item.setCheckState(qt.Qt.Checked)

	def onFrameVolCBox(self):
		"""
		Slot for ``Frame Volume:`` combo box
		"""
		if self.ui.frameVolCBox.currentNode() is not None:
			self.frameVolume = self.ui.frameVolCBox.currentNode()
			[self.ui.frameVolCBox.nodeFromIndex(i).SetAttribute('regVol', '1') for i in range(self.ui.frameVolCBox.nodeCount()) if self.ui.frameVolCBox.nodeFromIndex(i).GetName() != self.frameVolCBox.GetName()]
			self.frameVolume.SetAttribute('frameVol', '1')
			self.frameVolume.SetAttribute('regVol', '0')

	def getRegParameters(self,regAlgorithm,templateParams=False):
		if regAlgorithm.startswith('flirtRegAlgo'):
			interp = {
				'TriLinear':'trilinear', 
				'NearestNeighbour': 'nearestneighbour',
				'Sinc': 'sinc',
				'Spline':'spline'
			}
			cost = {
				'MutualInfo': 'mutualinfo',
				'CorRatio': 'corratio',
				'NormCorr': 'normcorr',
				'NormMI': 'normmi',
				'LeastSq': 'leastsq',
				'LabelDiff': 'labeldiff',
				'BBR': 'bbr'
			}
			regAlgo = {
				'regAlgo':'flirt',
				'parameters':{
					'cost': cost[self.ui.flirtCostCB.currentText] if not templateParams else cost[self.ui.flirtCostTemplateCB.currentText],
					'searchcost': cost[self.ui.flirtSearchCostCB.currentText] if not templateParams else cost[self.ui.flirtSearchCostTemplateCB.currentText],
					'interp': interp[self.ui.flirtInterpCB.currentText] if not templateParams else interp[self.ui.flirtInterpTemplateCB.currentText],
					'coarsesearch': self.ui.flirtCoarseSearchSB.value if not templateParams else self.ui.flirtCoarseSearchTemplateSB.value,
					'finesearch': self.ui.flirtFineSearchSB.value if not templateParams else self.ui.flirtFineSearchTemplateSB.value
				}
			}
		elif regAlgorithm.startswith('niftyRegAlgo'):
			interp = {
				'NearestNeighbour': 0, 
				'Linear': 1,
				'Cubic': 3,
				'Sinc': 4
			}
			DOF = {
				'6': '-rigOnly', 
				'12': ''
			}
			regAlgo = {
				'regAlgo': 'reg_aladin', 
				'parameters':{
					'interp': interp[self.ui.regaladinInterpCB.currentText] if not templateParams else interp[self.ui.regaladinInterpTemplateCB.currentText],
					'dof':  DOF[self.ui.regaladinDOFCB.currentText] if not templateParams else DOF['12'],
				}
			}
		elif regAlgorithm.startswith('antsRegAlgo'):
			interp = {
				'Linear': 'Linear', 
				'NearestNeighbour': 'NearestNeighbor',
				'BSpline': 'BSpline[3]',
				'GenericLabel': 'GenericLabel[Linear]'
			}
			metric_params = {
				'CrossCorr': '1,32,Regular,0.25',
				'MutualInfo': '1,4,Regular,0.25',
				'GlobalCorr': '1,15,Random,0.05'
			}
			regAlgo = {
				'regAlgo':'antsRegistration',
				'parameters':{
					'gradientstep': self.ui.gradientStepSB.value if not templateParams else self.ui.gradientStepTemplateSB.value,
					'interpolation': interp[self.ui.antsInterpCB.currentText] if not templateParams else interp[self.ui.antsInterpTemplateCB.currentText],
					'metric': self.ui.antsMetricCB.currentText if not templateParams else self.ui.antsMetricTemplateCB.currentText,
					'metric_params': metric_params[self.ui.antsMetricCB.currentText] if not templateParams else self.ui.antsMetricTemplateCB.currentText,
					'convergence': self.ui.convergence.text if not templateParams else self.ui.convergenceTemplate.text,
					'shrink-factors':self.ui.shrinkFactors.text if not templateParams else self.ui.shrinkFactorsTemplate.text,
					'smoothing-sigmas':self.ui.smoothingSigmas.text if not templateParams else self.ui.smoothingSigmasTemplate.text
				}
			}
		elif regAlgorithm.startswith('antsQuickRegAlgo'):
			if templateParams:
				children = self.ui.antsSynParametersTemplateGB.findChildren('QRadioButton')
			else:
				children = self.ui.antsQuickParametersGB.findChildren('QRadioButton')
			
			for i in children:
				if i.isChecked():
					if i.text == 'Yes':
						histMatch = 1
					else:
						histMatch = 0
			interp = {
				'Linear':'Linear', 
				'NearestNeighbour': 'NearestNeighbor',
				'BSpline': 'BSpline[3]',
				'GenericLabel':'GenericLabel[Linear]'
			}
			transform = {
				'Rig':'r', 
				'Rig+Affine': 'a',
				'Rig+Affine+Syn': 's',
				'Rig+Syn': 'sr',
				'Rig+Affine+BSpline Syn':'b',
				'Rig+BSpline Syn':'br',
			}
			regAlgo = {
				'regAlgo':'antsRegistrationQuick',
				'parameters':{
					'transform': transform[self.ui.antsQuickTransformTypeCB.currentText] if not templateParams else transform[self.ui.transformTypeTemplateCB.currentText],
					'interpolation': interp[self.ui.antsQuickInterpCB.currentText] if not templateParams else interp[self.ui.antsQuickInterpTemplateCB.currentText],
					'num_threads': self.ui.antsQuickNumThreads.value if not templateParams else self.ui.numThreadsTemplate.value,
					'histMatch': histMatch
				}
			}

		return regAlgo

	def onRunRegistrationButton(self):
		"""
		Slot for ``Run Registration`` button
		
		"""
		if self.ui.referenceComboBox.currentText != '' or self.ui.floatingComboBox.currentText != '':
			warningBox('You need to first confirm/decline the current registration result.')
			return

		if self.ui.frameVolCBox.currentNode() is not None:
			self.frameVolume = self.ui.frameVolCBox.currentNode()
			self.frameVolumeName = self.frameVolume.GetName() + '_coreg'
			[self.ui.frameVolCBox.nodeFromIndex(i).SetAttribute('regVol', '1') for i in range(self.ui.frameVolCBox.nodeCount()) if self.ui.frameVolCBox.nodeFromIndex(i).GetName() != self.frameVolume.GetName()]
			self.frameVolume.SetAttribute('frameVol', '1')
			self.frameVolume.SetAttribute('regVol', '0')

		if self.ui.referenceVolCBox.currentNode() is None:
			if self.ui.templateSpaceCB.currentText == 'Select template':
				warningBox('Please choose a reference volume.')
				return
			else:
				if self.ui.referenceVolTemplateCBox.currentNode() is None:
					warningBox('Please choose a reference volume.')
					return
				else:
					self.referenceVolume=self.ui.referenceVolTemplateCBox.currentNode()

		registerTemplate = False
		templateSpace = self.ui.templateSpaceCB.currentText
		if templateSpace != 'Select template' and templateSpace != 'None':
			registerTemplate = True

		children = self.ui.regAlgorithmTemplateGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked() == True and 'RegAlgo' in i.name:
				regAlgoTemplate=self.getRegParameters(i.name,True)
		
		children = self.ui.regAlgorithmGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked() == True and 'RegAlgo' in i.name:
				self.regAlgo=self.getRegParameters(i.name,False)
		
		self.regAlgo['registerTemplate']=registerTemplate
		self.regAlgo['templateSpace']=templateSpace
		self.regAlgo['regAlgoTemplateParams']=regAlgoTemplate

		if registerTemplate:
			if os.path.exists(os.path.join( self._parameterNode.GetParameter('derivFolder'), 'space')):
				registrationTemplateDone=[]
				for root, directories, filenames in os.walk(os.path.join( self._parameterNode.GetParameter('derivFolder'), 'space')):
					for filename in filenames:
						if templateSpace in filename:
							registrationTemplateDone.append(os.path.join(root, filename))

				if registrationTemplateDone:
					parent = None
					for w in slicer.app.topLevelWidgets():
						if hasattr(w,'objectName'):
							if w.objectName == 'qSlicerMainWindow':
								parent=w
					
					qm = qt.QMessageBox()
					ret = qm.question(parent, '', f"Registration to {templateSpace} space has already been run, would you like to re-run?", qm.Yes | qm.No)
					if ret == qm.No:
						self.regAlgo['registerTemplate']=False
					else:
						volumes = [x for x in slicer.util.getNodesByClass('vtkMRMLScalerVolumeNode')]
						for ivol in volumes:
							if f"{templateSpace}" in ivol.GetName():
								slicer.mrmlScene.RemoveNode(slicer.util.getNode(ivol.GetID()))

						transforms = [x for x in slicer.util.getNodesByClass('vtkMRMLLinearTransformNode')]
						for itrans in transforms:
							if f"{templateSpace}" in itrans.GetName():
								slicer.mrmlScene.RemoveNode(slicer.util.getNode(itrans.GetID()))

						for ifile in registrationTemplateDone:
							os.remove(ifile)


		if self.registrationInProgress:
			self.registrationInProgress = False
			self.logic.abortRequested = True
			self.ui.runRegistrationButton.setText('Cancelling...')
			return
		
		self.registrationInProgress = True
		self.ui.runRegistrationButton.setText('Cancel')
		slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
		
		try:
			files = [x for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'))) if any(x.endswith(y) for y in {'.nii', '.nii.gz'})]
			file_sidecar = []
			for f in files:
				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + '.json')) as (file):
					filenames = json.load(file)
				if filenames['node_name'] == self.referenceVolume.GetName():
					file_sidecar = filenames
					break

			file_sidecar['vol_type'] = 'reference'
			json_output = json.dumps(file_sidecar, indent=4)

			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + '.json'), 'w') as (fid):
				fid.write(json_output)
				fid.write('\n')

			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + '.json')) as (file):
				file_sidecar = json.load(file)

			referenceVolumeInfo = [self.referenceVolume, file_sidecar['file_name']]
			movingVolumeNode = []
			if self.ui.referenceVolCBox.currentNode() is not None:
				imageVolumes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
				floatVolsCheck=self.regFloatingCB.check_items()

				for iimage in imageVolumes:
					if iimage.GetName() != self.referenceVolume.GetName() and iimage.GetName() in floatVolsCheck:
						files = [x for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'))) if any(x.endswith(y) for y in {'.nii', '.nii.gz'})]
						file_sidecar = []
						for f in files:
							with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + '.json')) as (file):
								filenames = json.load(file)
							if filenames['node_name'] == iimage.GetName():
								file_sidecar = filenames
								break
						if not file_sidecar:
							files = [x for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'),'frame')) if any(x.endswith(y) for y in {'.nii', '.nii.gz'})]
							file_sidecar = []
							for f in files:
								with open(os.path.join(self._parameterNode.GetParameter('derivFolder'),'frame', f.split('.nii')[0] + '.json')) as (file):
									filenames = json.load(file)
								if filenames['node_name'] == iimage.GetName():
									file_sidecar = filenames
									break

						if not file_sidecar['coregistered']:
							movingVolumeNode.append([iimage, file_sidecar['file_name']])

			self.ui.statusLabel.setMinimumHeight(15 * (5 + len(movingVolumeNode)))
			slicer.app.processEvents()

			self.logic.registerVolumes(referenceVolumeInfo, movingVolumeNode, self._parameterNode.GetParameter('derivFolder'), self.regAlgo)

		finally:
			slicer.app.restoreOverrideCursor()
			self.registrationInProgress = False
			self.ui.runRegistrationButton.setText('Run Registration')

		self.ui.referenceComboBox.addItems([self.referenceVolume.GetName()])
		for ifile in movingVolumeNode:
			self.ui.floatingComboBox.addItems([ifile[0].GetName() + '_coreg'])
			self.ui.floatingComboBox.setCurrentIndex(self.ui.floatingComboBox.findText(ifile[0].GetName() + '_coreg'))

		if self.regAlgo['registerTemplate']:
			volumes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
			for ivol in volumes:
				if f"space-{self.regAlgo['templateSpace']}_desc-affine" in ivol.GetName():
					self.ui.floatingComboBox.addItem(ivol.GetName())

		slicer.util.setSliceViewerLayers(background=self.referenceVolume, foreground=None)
		#slicer.util.resetSliceViews()

		self.firstCompare = True
		self.onCompareVolumes()

		slicer.util.messageBox('Confirm/decline each registration by using the\ngreen and red buttons under "Co-registered Volumes"',
			dontShowAgainSettingsKey = "MainWindow/DontShowCheckRegistration")

	def addLog(self, text):
		self.ui.statusLabel.appendPlainText(text)
		slicer.app.processEvents()  # force update
	

#
# registrationLogic
#


class registrationLogic(ScriptedLoadableModuleLogic):
	"""
	**Contructor - Main registrationLogic object**

	This class implements all the actual computation done by trajectoryGuide.  

	Uses ScriptedLoadableModuleLogic base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""
	def __init__(self):
		ScriptedLoadableModuleLogic.__init__(self)

		self.logCallback = None
		self.logStandardOutput = False
		self.abortRequested = False
		self.scriptPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

		import platform
		if platform.system() == 'Windows':
			self.fslBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'fsl')
			self.flirtExe = 'flirt.exe'
			self.fnirtExe = 'fnirt.exe'
			
			self.antsBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.antsExe = 'antsRegistration.exe'
			
			self.antsSynBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.antsSynExe = 'antsRegistrationSyN.sh'

			self.convTransBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.convTransExe = 'ConvertTransformFile.exe'

			self.niftyBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'niftyReg', 'windows')
			self.niftyExe = 'reg_aladin.exe'
			
			self.c3dBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'c3d')
			self.c3dExe = 'c3d_affine_tool.exe'

		elif platform.system().lower() == 'linux':
			os.chmod(os.path.abspath(__file__), 511)
			self.fslBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'fsl')
			self.flirtExe = 'flirt.glnxa64'
			self.fnirtExe = 'fnirt.glnxa64'
			
			self.antsBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.antsExe = 'antsRegistration.glnxa64'
			
			self.antsSynBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.antsSynExe = 'antsRegistrationSyNQuick.sh'

			self.convTransBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.convTransExe = 'ConvertTransformFile.gnxa64'

			self.niftyBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'niftyReg', 'linux', 'bin')
			self.niftyExe = 'reg_aladin'
			
			self.c3dBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'c3d')
			self.c3dExe = 'c3d_affine_tool'
			
			os.chmod(os.path.join(self.niftyBinDir, self.niftyExe), 511)
			os.chmod(os.path.join(self.c3dBinDir, self.c3dExe), 511)
		
		elif platform.system() == 'Darwin':
			self.fslBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'fsl')
			self.flirtExe = 'flirt.maci64'
			self.fnirtExe = 'fnirt.maci64'
			
			self.antsBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.antsExe = 'antsRegistration.maci64'
			
			self.convTransBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.convTransExe = 'ConvertTransformFile.maci64'
			
			self.antsSynBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'ants')
			self.antsSynExe = 'antsRegistrationSyN.sh'
			
			self.niftyBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'niftyReg', 'osX', 'bin')
			self.niftyExe = 'reg_aladin'
			
			self.c3dBinDir = os.path.join(self.scriptPath, 'resources', 'ext_libs', 'c3d')
			self.c3dExe = 'c3d_affine_tool'

	def getParameterNode(self, replace=False):
		"""Get the registration parameter node.

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
		""" Create the registration parameter node.

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
						os.path.join(parameterNode.GetParameter("trajectoryGuidePath"),'resources', 'settings', 'model_visibility.json'),
						os.path.join(parameterNode.GetParameter('derivFolder'), ipath, 'model_visibility.json')
					)
					shutil.copy2(
						os.path.join(parameterNode.GetParameter("trajectoryGuidePath"), 'resources', 'settings', 'model_color.json'),
						os.path.join(parameterNode.GetParameter('derivFolder'), ipath, 'model_color.json')
					)

	def _addCustomLayouts(self):

		addCustomLayouts()
		slicer.app.layoutManager().setLayout(slicerLayout)

	def addLog(self, text):
		"""
		Adds text to the log. 
		:param text: the text to add
		: type text: string
		"""
		logging.info(text)
		if self.logCallback:
			self.logCallback(text)
		slicer.app.processEvents()

	def getRegBinDir(self, regAlgo):
		"""
		Gets the regular bin directory
		:param regAlgo: 
		:type regAlgo: Integer
		:return self.fslBinDir: 
		:return self.antsBinDir:
		:return self.niftyBinDir:

		"""
		try:
			if regAlgo == 'flirt':
				if self.fslBinDir:
					return self.fslBinDir
			elif regAlgo == 'antsRegistration':
				if self.antsBinDir:
					return self.antsBinDir
			elif regAlgo == 'antsRegistrationQuick':
				if self.antsSynBinDir:
					return self.antsSynBinDir
			elif regAlgo == 'reg_aladin':
				if self.niftyBinDir:
					return self.niftyBinDir
			elif regAlgo == 'c3d':
				if self.c3dBinDir:
					return self.c3dBinDir
		except:
			raise ValueError(f'{regAlgo} not found')

	def getRegEnv(self, regAlgo):
		"""
		Creates an environment where executables are added to the path
		:param regAlgo:
		"""
		regBinDir = self.getRegBinDir(regAlgo['regAlgo'])
		regEnv = os.environ.copy()
		regEnv['PATH'] = regBinDir + os.pathsep + regEnv['PATH'] if regEnv.get('PATH') else regBinDir

		if any([x in sys.platform.lower() for x in ('linux', 'darwin')]):
			if regAlgo['regAlgo'] in ('flirt','reg_aladin'):
				regLibDir = os.path.abspath(os.path.join(regBinDir, '../lib'))
				regEnv['LD_LIBRARY_PATH'] = regLibDir + os.pathsep + regEnv['LD_LIBRARY_PATH'] if regEnv.get('LD_LIBRARY_PATH') else regLibDir
				regEnv['FSLOUTPUTTYPE'] = 'NIFTI_GZ'
			elif regAlgo['regAlgo'] in ('antsRegistration','antsRegistrationQuick'):
				regEnv['ANTSPATH'] = regBinDir
			elif regAlgo['regAlgo'] == 'c3d':
				regLibDir = os.path.abspath(os.path.join(regBinDir, '../lib'))
				regEnv['LD_LIBRARY_PATH'] = regLibDir + os.pathsep + regEnv['LD_LIBRARY_PATH'] if regEnv.get('LD_LIBRARY_PATH') else regLibDir
		elif sys.platform.lower() =='win32' and any(x in regAlgo['regAlgo'] for x in ('antsRegistration','antsRegistrationQuick')):
			regEnv['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(regAlgo['parameters']['num_threads'])

		return regEnv

	def getStartupInfo(self):
		"""
		Gets the startup information
		"""
		if sys.platform != 'win32':
			return
		else:
			import subprocess
			info = subprocess.STARTUPINFO()
			info.dwFlags = 1
			info.wShowWindow = 0
			return info

	def run_command(self, command):
		regEnv = os.environ.copy()
		regEnv['PATH'] = self.c3dBinDir + ':' + regEnv['PATH']
		regLibDir = os.path.abspath(os.path.join(self.c3dBinDir, '../lib'))
		regEnv['LD_LIBRARY_PATH'] = regLibDir + ':' + regEnv['LD_LIBRARY_PATH']
		return subprocess.Popen(command, env=regEnv, stdout=(subprocess.PIPE), universal_newlines=True, startupinfo=(self.getStartupInfo()), shell=True)

	def startReg(self, cmdLineArguments, logText, regAlgo):
		"""
		Initiates registration specific to the system's platform
		:param cmdLineArguments: command line arguments
		:param logText: Log text.
		:param regAlgo: registration algorithm

		:return subprocess:

		"""
		self.addLog(logText)
		
		if regAlgo['regAlgo'] == 10:
			return subprocess.Popen(cmdLineArguments, env=slicer.util.startupEnvironment(), stdout=(subprocess.PIPE),
				  universal_newlines=True,
				  shell=True)
		else:
			if sys.platform == 'win32':
				return subprocess.Popen(cmdLineArguments, env=(self.getRegEnv(regAlgo)), stdout=(subprocess.PIPE),
				  universal_newlines=True,
				  startupinfo=(self.getStartupInfo()),
				  shell=True)
			else:
				return subprocess.Popen(cmdLineArguments, env=(self.getRegEnv(regAlgo)), stdout=(subprocess.PIPE),
				  universal_newlines=True,
				  shell=True)

	def logProcessOutput(self, process):
		"""
		Saves process output (if not logged) so that it can be displayed in case of an error.
		:param process: the process so far. 

		"""
		processOutput = ''
		import subprocess
		for stdout_line in iter(process.stdout.readline, ''):
			if self.logStandardOutput:
				self.addLog(stdout_line.rstrip())
			else:
				processOutput += stdout_line.rstrip() + '\n'
			slicer.app.processEvents()
			if self.abortRequested:
				process.kill()

		process.stdout.close()
		return_code = process.wait()
		if return_code:
			if self.abortRequested:
				raise ValueError('User requested cancel.')
			elif processOutput:
					self.addLog(processOutput)
			else:
				raise subprocess.CalledProcessError(return_code, 'registration')

	def getTempDirectoryBase(self):
		"""
		Gets the temporary directory base path

		:return dirPath: the directory path.
		:return type: String
		"""
		tempDir = qt.QDir(slicer.app.temporaryPath)
		fileInfo = qt.QFileInfo(qt.QDir(tempDir), 'Reg')
		dirPath = fileInfo.absoluteFilePath()
		qt.QDir().mkpath(dirPath)
		return dirPath

	def createTempDirectory(self):
		"""
		Creates temporary directory. 
		:return dirPath: the temporary directory'a path
		:return type: string
		"""
		import qt, slicer
		tempDir = qt.QDir(self.getTempDirectoryBase())
		tempDirName = qt.QDateTime().currentDateTime().toString('yyyyMMdd_hhmmss_zzz')
		fileInfo = qt.QFileInfo(qt.QDir(tempDir), tempDirName)
		dirPath = fileInfo.absoluteFilePath()
		qt.QDir().mkpath(dirPath)
		return dirPath

	def registerVolumes(self, fixedVolumeNode, movingVolumeNode, derivFolder, regAlgo):
		self.regAlgo = regAlgo
		
		if movingVolumeNode:
			derivFolderTemp = os.path.join(derivFolder, 'temp')
			if not os.path.exists(derivFolderTemp):
				os.makedirs(derivFolderTemp)

		if self.regAlgo['registerTemplate']:
			derivFolderTemp = os.path.join(derivFolder, 'temp')
			if not os.path.exists(derivFolderTemp):
				os.makedirs(derivFolderTemp)
			spaceDataDir = os.path.join(derivFolder, 'space')
			if not os.path.exists(spaceDataDir):
				os.makedirs(spaceDataDir)

		self.abortRequested = False
		tempDir = self.createTempDirectory()
		inputDir = os.path.join(tempDir, 'input')
		qt.QDir().mkpath(inputDir)
		outputDir = os.path.join(tempDir, 'output')
		qt.QDir().mkpath(outputDir)

		fixedVolume = os.path.normpath(os.path.join(inputDir, fixedVolumeNode[1]))
		slicer.util.saveNode(fixedVolumeNode[0], fixedVolume, {'useCompression': False})
		
		self.addLog('Registration started in working directory: ' + tempDir)
		self.addLog('Patient registration performed using: ' + self.regAlgo['regAlgo'])
		
		if 'parameters' in list(self.regAlgo):
			self.addLog('Patient registration parameters: ')
			for k, v in self.regAlgo['parameters'].items():
				self.addLog(k + ' -> ' + str(v))

		if self.regAlgo['registerTemplate']:
			self.addLog('Template registration performed using: ' + self.regAlgo['regAlgo'])
			self.addLog('Template registration space: ' + str(self.regAlgo['templateSpace']))
			if 'parameters' in list(self.regAlgo['regAlgoTemplateParams']):
				self.addLog('Template registration parameters: ')
				for k, v in self.regAlgo['regAlgoTemplateParams']['parameters'].items():
					self.addLog(k + ' -> ' + str(v))
		
		cnt = 1
		for ivol in movingVolumeNode:
			movingVolume = os.path.normpath(os.path.join(inputDir, ivol[1]))
			slicer.util.saveNode(ivol[0], movingVolume, {'useCompression': False})
			movingVolFilename = ivol[1].split('.nii')[0]
			
			resultTransformPath = os.path.normpath(os.path.join(outputDir, ivol[1].split('.nii')[0]))
			outputVolume = os.path.normpath(os.path.join(outputDir, ivol[1].split('.nii')[0] + '_coreg'))

			if self.regAlgo['regAlgo'] == 'flirt':

				reg_cmd = ' '.join([
					os.path.join(self.fslBinDir, self.flirtExe),
					f"-in {movingVolume}",
					f"-ref {fixedVolume}",
					f"-out {outputVolume}.nii.gz",
					f"-omat {resultTransformPath}_coregmatrix.mat",
					"-dof 6",
					f"-cost {self.regAlgo['parameters']['cost']}",
					f"-searchcost {self.regAlgo['parameters']['searchcost']}",
					f"-interp {self.regAlgo['parameters']['interp']}",
					f"-coarsesearch {self.regAlgo['parameters']['coarsesearch']}",
					f"-finesearch {self.regAlgo['parameters']['finesearch']}",
					"-v"
				])

			elif self.regAlgo['regAlgo'] == 'antsRegistration':

				rigidstage = ' '.join([
					f"--initial-moving-transform [{fixedVolume},{movingVolume},1]",
					f"--transform Rigid[{self.regAlgo['parameters']['gradientstep']}]",
					f"--metric {self.regAlgo['parameters']['metric']}[{fixedVolume},{movingVolume},{self.regAlgo['parameters']['metric_params']}]",
					f"--convergence [ {self.regAlgo['parameters']['convergence']} ]",
					f"--shrink-factors {self.regAlgo['parameters']['shrink-factors']}",
					f"--smoothing-sigmas {self.regAlgo['parameters']['smoothing-sigmas']}"
				])

				reg_cmd = ' '.join([
					os.path.join(self.antsBinDir, self.antsExe),
					'--verbose 1',
					'--dimensionality 3',
					'--float 1',
					"--collapse-output-transforms 1",
					f"--output [{resultTransformPath}_coreg,{outputVolume}.nii.gz]",
					f"--interpolation {self.regAlgo['parameters']['interpolation']}",
					'--use-histogram-matching 1',
					'--winsorize-image-intensities [0.005,0.995]',
					rigidstage
				])

			elif self.regAlgo['regAlgo'] == 'antsRegistrationQuick':
				
				numOfBins=32
				splineDistance=26
				collapseOutputTransforms=1

				rigidConvergence="[ 1000x500x250x0,1e-6,10 ]"
				rigidShrinkFactors="8x4x2x1"
				rigidSmoothingSigmas="3x2x1x0vox"

				affineConvergence="[ 1000x500x250x0,1e-6,10 ]"
				affineShrinkFactors="8x4x2x1"
				affineSmoothingSigmas="3x2x1x0vox"

				synConvergence="[ 100x70x50x0,1e-6,10 ]"
				synShrinkFactors="8x4x2x1"
				synSmoothingSigmas="3x2x1x0vox"

				tx='Rigid'

				rigidStage=' '.join([
					f"--initial-moving-transform [{fixedVolume},{movingVolume},1]",
					f"--metric MI[{fixedVolume},{movingVolume},1,32,Regular,0.25 ]",
					f"--transform {tx}[0.1]",
					f"--convergence {rigidConvergence}",
					f"--shrink-factors {rigidShrinkFactors}",
					f"--smoothing-sigmas {rigidSmoothingSigmas}"
				])

				affineStage=' '.join([
					f"--transform Affine[0.1]",
					f"--metric MI[{fixedVolume},{movingVolume},1,32,Regular,0.25 ]",
					f"--convergence {affineConvergence}",
					f"--shrink-factors {affineShrinkFactors}",
					f"--smoothing-sigmas {affineSmoothingSigmas}"
				])

				if any(transform == self.regAlgo['parameters']['transform'] for transform in ("r","t")):
					stages=f"{rigidStage}"
					numRegStages=1
				elif self.regAlgo['parameters']['transform'] == "a":
					stages=f"{rigidStage} {affineStage}"
					numRegStages=2

				reg_cmd = ' '.join([
					os.path.join(self.antsBinDir, self.antsExe),
					'--verbose 1',
					'--dimensionality 3',
					'--float 1',
					f"--collapse-output-transforms {collapseOutputTransforms}",
					f"--output [{resultTransformPath}_coreg,{outputVolume}.nii.gz]",
					f"--interpolation {self.regAlgo['parameters']['interpolation']}",
					f"--use-histogram-matching {self.regAlgo['parameters']['histMatch']}",
					'--winsorize-image-intensities [0.005,0.995]',
					stages
				])

				if sys.platform != 'win32':
					reg_cmd = f"export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS={self.regAlgo['parameters']['num_threads']}&&" + reg_cmd

			elif self.regAlgo['regAlgo'] == 'reg_aladin':

				reg_cmd = ' '.join([
					os.path.join(self.niftyBinDir, self.niftyExe),
					f"-ref {fixedVolume}",
					f"-flo {movingVolume}",
					f"{self.regAlgo['parameters']['dof']}",
					f"-interp {self.regAlgo['parameters']['interp']}",
					f"-aff {resultTransformPath}_coregmatrix.txt",
					f"-res {outputVolume}.nii.gz",
					'-speeeeed'
				])

			
			logText = 'Register volumes {} of {}: {} to {}'.format(str(cnt), str(len(movingVolumeNode)), ivol[0].GetName(), fixedVolumeNode[0].GetName())
			cnt += 1
			ep = self.startReg(reg_cmd, logText, self.regAlgo)
			self.logProcessOutput(ep)
			
			if 'acq-' in ivol[0].GetName().lower():
				acq_str=[x for x in ivol[0].GetName().split('_') if 'acq' in x][0]
				if 'frame' in acq_str.lower():
					transformName=ivol[0].GetName().split('_')[-1]+acq_str.split('-')[-1]
				else:
					transformName=acq_str.split('-')[-1]+ivol[0].GetName().split('_')[-1]
			else:
				transformName=ivol[0].GetName().split('_')[-1]

			if self.regAlgo['regAlgo'] == 'reg_aladin':
				matrix = self.readRegMatrix(resultTransformPath+'_coregmatrix.txt')
				vtkMatrix = self.getVTKMatrixFromNumpyMatrix(matrix)
				resultTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode')
				resultTransformNode.SetMatrixTransformFromParent(vtkMatrix)
				resultTransformNode.SetName(f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-rigid_from-{transformName}_to-{fixedVolumeNode[0].GetName().split('_')[-1]}_xfm")
				transformNodeFilename = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-rigid_from-{transformName}_to-{fixedVolumeNode[0].GetName().split('_')[-1]}_xfm.tfm")
				slicer.util.saveNode(resultTransformNode, transformNodeFilename, {'useCompression': False})

			elif self.regAlgo['regAlgo'] == 'flirt':
				transformNodeFilename = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-rigid_from-{transformName}_to-{fixedVolumeNode[0].GetName().split('_')[-1]}_xfm.tfm")
				
				import subprocess
				c3d_cmd=[os.path.join(self.c3dBinDir,self.c3dExe),'-ref', fixedVolume,'-src',movingVolume,resultTransformPath+'_coregmatrix.mat','-fsl2ras','-oitk',transformNodeFilename]
				command_result = subprocess.run(c3d_cmd, env=slicer.util.startupEnvironment())

				with open(transformNodeFilename, 'r') as (infile):
					lines = infile.readlines()

				lines[2] = 'Transform: AffineTransform_double_3_3\n'
				with open(transformNodeFilename, 'w') as (fid):
					for i in range(len(lines)):
						fid.write(lines[i])

				node = slicer.util.loadTransform(transformNodeFilename)
			
			elif self.regAlgo['regAlgo'] in ('antsRegistration','antsRegistrationQuick'):
				transformNodeFilename = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-rigid_from-{transformName}_to-{fixedVolumeNode[0].GetName().split('_')[-1]}_xfm.txt")

				import subprocess
				convertTransform_cmd=[os.path.join(self.convTransBinDir,self.convTransExe),'3',resultTransformPath + '_coreg0GenericAffine.mat',transformNodeFilename,'--hm','--ras']
				command_result = subprocess.run(convertTransform_cmd, env=slicer.util.startupEnvironment())

				transformMatrix = self.readRegMatrix(transformNodeFilename)
				vtkTransformMatrix = self.getVTKMatrixFromNumpyMatrix(transformMatrix)
				resultTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode')
				resultTransformNode.SetMatrixTransformFromParent(vtkTransformMatrix)
				resultTransformNode.SetName(f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-rigid_from-{transformName}_to-{fixedVolumeNode[0].GetName().split('_')[-1]}_xfm")
				transformNodeFilenameNew = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-rigid_from-{transformName}_to-{fixedVolumeNode[0].GetName().split('_')[-1]}_xfm.tfm")
				slicer.util.saveNode(resultTransformNode, transformNodeFilenameNew, {'useCompression': False})

				os.remove(transformNodeFilename)

				#shutil.copy2(os.path.join(outputDir, ivol[1].split('.nii')[0] + '_coreg.nii.gz'), outputVolume)

			if not self.abortRequested:
				loadedOutputVolumeNode = []
				loadedOutputVolumeNode = slicer.util.loadVolume(outputVolume+'.nii.gz')
				slicer.util.getNode(loadedOutputVolumeNode.GetID()).SetName(ivol[0].GetName() + '_coreg')
				if loadedOutputVolumeNode:
					if fixedVolumeNode[0].GetTransformNodeID() is not None:
						loadedOutputVolumeNode.SetAndObserveTransformNodeID(fixedVolumeNode[0].GetTransformNodeID())
					slicer.util.saveNode(loadedOutputVolumeNode, os.path.join(derivFolderTemp, movingVolFilename + '_coreg.nii.gz'), {'useCompression': False})
				else:
					self.addLog('Failed load of output volume: ' + outputVolume + '\n')

		if self.regAlgo['registerTemplate']:
			self.ref_template = glob.glob(os.path.normpath(os.path.join(self.scriptPath, 'resources', 'ext_libs', 'space', 'tpl-' + self.regAlgo['templateSpace'], 'templates','*_T1w.nii.gz')))
			
			if self.ref_template:
				self.ref_template = self.ref_template[0]

			resultTransformPath = os.path.normpath(os.path.join(outputDir, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}"))
			outputVolume = os.path.normpath(os.path.join(outputDir, f"{os.path.basename(derivFolder).replace(' ', '_')}_space-{self.regAlgo['templateSpace']}_T1w"))

			if self.regAlgo['regAlgoTemplateParams']['regAlgo'] == 'flirt':

				reg_cmd = ' '.join([
					os.path.join(self.fslBinDir, self.flirtExe),
					f"-in {fixedVolume}",
					f"-ref {self.ref_template}",
					f"-out {outputVolume}.nii.gz",
					f"-omat {resultTransformPath}_xfm.mat",
					"-dof 12",
					f"-cost {self.regAlgo['regAlgoTemplateParams']['parameters']['cost']}",
					f"-searchcost {self.regAlgo['regAlgoTemplateParams']['parameters']['searchcost']}",
					f"-interp {self.regAlgo['regAlgoTemplateParams']['parameters']['interp']}",
					f"-coarsesearch {self.regAlgo['regAlgoTemplateParams']['parameters']['coarsesearch']}",
					f"-finesearch {self.regAlgo['regAlgoTemplateParams']['parameters']['finesearch']}",
					'-v'
					])

			elif self.regAlgo['regAlgoTemplateParams']['regAlgo'] == 'antsRegistration':

				rigidstage = ' '.join([
					f"--initial-moving-transform [{self.ref_template},{fixedVolume},1]",
					f"--transform Rigid[{self.regAlgo['regAlgoTemplateParams']['parameters']['gradientstep']}]",
					f"--metric {self.regAlgo['regAlgoTemplateParams']['parameters']['metric']}[{self.ref_template},{fixedVolume},{self.regAlgo['regAlgoTemplateParams']['parameters']['metric_params']}]",
					f"--convergence [ {self.regAlgo['regAlgoTemplateParams']['parameters']['convergence']} ]",
					f"--shrink-factors {self.regAlgo['regAlgoTemplateParams']['parameters']['shrink-factors']}",
					f"--smoothing-sigmas {self.regAlgo['regAlgoTemplateParams']['parameters']['smoothing-sigmas']}"
				])

				affinestage = ' '.join([
					f"--transform Affine[{self.regAlgo['regAlgoTemplateParams']['parameters']['gradientstep']}]",
					f"--metric {self.regAlgo['regAlgoTemplateParams']['parameters']['metric']}[{self.ref_template},{fixedVolume},{self.regAlgo['regAlgoTemplateParams']['parameters']['metric_params']}]",
					f"--convergence [ {self.regAlgo['regAlgoTemplateParams']['parameters']['convergence']} ]",
					f"--shrink-factors {self.regAlgo['regAlgoTemplateParams']['parameters']['shrink-factors']}",
					f"--smoothing-sigmas {self.regAlgo['regAlgoTemplateParams']['parameters']['smoothing-sigmas']}"
				])

				reg_cmd = ' '.join([
					os.path.join(self.antsBinDir, self.antsExe),
					'--verbose 1',
					'--dimensionality 3',
					'--float 1',
					"--collapse-output-transforms 1",
					f"--output [{resultTransformPath}_xfm,{outputVolume}.nii.gz",
					f"--interpolation {self.regAlgo['regAlgoTemplateParams']['parameters']['interpolation']}",
					'--use-histogram-matching 1',
					'--winsorize-image-intensities [0.005,0.995]',
					rigidstage,
					affinestage
				])

			elif self.regAlgo['regAlgoTemplateParams']['regAlgo'] == 'antsRegistrationQuick':

				numOfBins=32
				splineDistance=26
				collapseOutputTransforms=1

				rigidConvergence="[ 1000x500x250x0,1e-6,10 ]"
				rigidShrinkFactors="8x4x2x1"
				rigidSmoothingSigmas="3x2x1x0vox"

				affineConvergence="[ 1000x500x250x0,1e-6,10 ]"
				affineShrinkFactors="8x4x2x1"
				affineSmoothingSigmas="3x2x1x0vox"

				synConvergence="[ 100x70x50x0,1e-6,10 ]"
				synShrinkFactors="8x4x2x1"
				synSmoothingSigmas="3x2x1x0vox"

				tx='Rigid'
				if self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] == "t":
					tx='Translation'

				rigidStage=' '.join([
					f"--initial-moving-transform [{self.ref_template},{fixedVolume},1]",
					f"--transform {tx}[0.1]",
					f"--metric MI[{self.ref_template},{fixedVolume},1,32,Regular,0.25]",
					f"--convergence {rigidConvergence}",
					f"--shrink-factors {rigidShrinkFactors}",
					f"--smoothing-sigmas {rigidSmoothingSigmas}"
				])

				affineStage=' '.join([
					f"--transform Affine[0.1]",
					f"--metric MI[{self.ref_template},{fixedVolume},1,32,Regular,0.25]",
					f"--convergence {affineConvergence}",
					f"--shrink-factors {affineShrinkFactors}",
					f"--smoothing-sigmas {affineSmoothingSigmas}"
				])

				synStage=' '.join([
					f"--metric MI[{self.ref_template},{fixedVolume},1,{numOfBins}]",
					f"--convergence {synConvergence}",
					f"--shrink-factors {synShrinkFactors}",
					f"--smoothing-sigmas {synSmoothingSigmas}"
				])

				if any(transform == self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] for transform in ('sr','br')):
					synStage=' '.join([
						f"--metric MI[{self.ref_template},{fixedVolume},1,{numOfBins}]",
						f"--convergence [50x0,1e-6,10]",
						f"--shrink-factors 2x1",
						f"--smoothing-sigmas 1x0vox"
					])

				
				if any(transform == self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] for transform in ('b','br','bo')):
					synStage=f"--transform BSplineSyN[0.1,{splineDistance},0,3] " + synStage

				if any(transform == self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] for transform in ('s','sr','so')):
					synStage="--transform SyN[0.1,3,0] " + synStage


				if any(transform == self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] for transform in ("r","t")):
					stages=f"{rigidStage}"
					numRegStages=1
				elif self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] == "a":
					stages=f"{rigidStage} {affineStage}"
					numRegStages=2
				elif any(transform == self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] for transform in ("b","s")):
					stages=f"{rigidStage} {affineStage} {synStage}"
					numRegStages=3
				elif any(transform == self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] for transform in ("br","sr")):
					stages=f"{rigidStage} {synStage}"
					numRegStages=2
				elif any(transform == self.regAlgo['regAlgoTemplateParams']['parameters']['transform'] for transform in ("bo","so")):
					stages=f"{affineStage}"
					numRegStages=1

				reg_cmd = ' '.join([
					os.path.join(self.antsBinDir, self.antsExe),
					'--verbose 1',
					'--dimensionality 3',
					'--float 1',
					f"--collapse-output-transforms {collapseOutputTransforms}",
					f"--output [{resultTransformPath}_coreg,{outputVolume}.nii.gz]",
					f"--interpolation {self.regAlgo['regAlgoTemplateParams']['parameters']['interpolation']}",
					f"--use-histogram-matching {self.regAlgo['regAlgoTemplateParams']['parameters']['histMatch']}",
					'--winsorize-image-intensities [0.005,0.995]',
					stages
				])
				
				if sys.platform != 'win32':
					reg_cmd = f"export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS={self.regAlgo['regAlgoTemplateParams']['parameters']['num_threads']}&&" + reg_cmd

			elif self.regAlgo['regAlgoTemplateParams']['regAlgo'] == 'reg_aladin':
				
				reg_cmd = ' '.join([
					os.path.join(self.niftyBinDir, self.niftyExe),
					f"-ref {self.ref_template}",
					f"-flo {fixedVolume}",
					f"{self.regAlgo['regAlgoTemplateParams']['parameters']['dof']}",
					f"-interp {self.regAlgo['regAlgoTemplateParams']['parameters']['interp']}",
					f"-aff {resultTransformPath}_xfm.txt",
					f"-res {outputVolume}.nii.gz",
					'-speeeeed'
				])
			
			logText = f"Registering {fixedVolumeNode[0].GetName()} to {self.regAlgo['templateSpace']} space"
			ep = self.startReg(reg_cmd, logText, self.regAlgo['regAlgoTemplateParams'])
			self.logProcessOutput(ep)
			
			if self.regAlgo['regAlgoTemplateParams']['regAlgo'] == 'reg_aladin':
				transformMatrix = self.readRegMatrix(resultTransformPath+'_xfm.txt')
				vtkTransformMatrix = self.getVTKMatrixFromNumpyMatrix(transformMatrix)
				resultTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode')
				resultTransformNode.SetMatrixTransformFromParent(vtkTransformMatrix)
				resultTransformNode.SetName(f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm")
				transformNodeFilename = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm.tfm")
				slicer.util.saveNode(resultTransformNode, transformNodeFilename, {'useCompression': False})
			
			elif self.regAlgo['regAlgoTemplateParams']['regAlgo'] == 'flirt':
				transformNodeFilename = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm.tfm")

				import subprocess
				c3d_cmd=[os.path.join(self.c3dBinDir,self.c3dExe),resultTransformPath+'_xfm.mat','-ref', self.ref_template,'-src',fixedVolume,'-fsl2ras','-oitk',transformNodeFilename]
				command_result = subprocess.run(c3d_cmd, env=slicer.util.startupEnvironment())

				with open(transformNodeFilename, 'r') as (infile):
					lines = infile.readlines()
				
				lines[2] = 'Transform: AffineTransform_double_3_3\n'
				with open(transformNodeFilename, 'w') as (fid):
					for i in range(len(lines)):
						fid.write(lines[i])

				resultTransformNode = slicer.util.loadTransform(transformNodeFilename)
				transformNodeFilename = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm.h5")
				slicer.util.saveNode(resultTransformNode, transformNodeFilename, {'useCompression': False})
				os.remove(transformNodeFilename)

			elif self.regAlgo['regAlgoTemplateParams']['regAlgo'] in ('antsRegistration','antsRegistrationQuick'):

				transformNodeFilename = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm.txt")

				import subprocess
				convertTransform_cmd=[os.path.join(self.convTransBinDir,self.convTransExe),'3',resultTransformPath + '_coreg0GenericAffine.mat',transformNodeFilename,'--hm','--ras']
				command_result = subprocess.run(convertTransform_cmd, env=slicer.util.startupEnvironment())

				transformMatrix = self.readRegMatrix(transformNodeFilename)
				vtkTransformMatrix = self.getVTKMatrixFromNumpyMatrix(transformMatrix)
				resultTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode')
				resultTransformNode.SetMatrixTransformFromParent(vtkTransformMatrix)
				resultTransformNode.SetName(f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm")
				transformNodeFilenameNew = os.path.join(derivFolderTemp, f"{os.path.basename(derivFolder).replace(' ', '_')}_desc-affine_from-subject_to-{self.regAlgo['templateSpace']}_xfm.h5")
				slicer.util.saveNode(resultTransformNode, transformNodeFilenameNew, {'useCompression': False})

				os.remove(transformNodeFilename)

				#shutil.copy2(os.path.join(outputDir, ivol[1].split('.nii')[0] + '_xfmWarped.nii.gz'), outputVolume+'.nii.gz')

			if not self.abortRequested:

				filenamePrefix = f"{os.path.basename(derivFolder).replace(' ', '_')}_space-{self.regAlgo['templateSpace']}_desc-affine_{os.path.basename(fixedVolume).split('.nii')[0].split('_')[-1]}"
				finalOutputVol=os.path.join(derivFolderTemp, filenamePrefix+'.nii.gz')
				shutil.copy2(outputVolume+'.nii.gz', finalOutputVol)

				loadedOutputVolumeNode = slicer.util.loadVolume(finalOutputVol)

				file_attrbs = {}
				file_attrbs['file_name'] = filenamePrefix+'.nii.gz'
				file_attrbs['node_name'] = filenamePrefix
				file_attrbs['window'] = 9370.0
				file_attrbs['level'] = 4700.0
				file_attrbs['coregistered'] = True
				file_attrbs['vol_type'] = 'moving'
				file_attrbs['reference'] = os.path.basename(self.ref_template).split('nii')[0]
				file_attrbs['registration']={
					'algorithm':self.regAlgo['regAlgoTemplateParams']['regAlgo'],
					'type':'nonlinear',
					'parameters':self.regAlgo['regAlgoTemplateParams']['parameters']
				}

				json_file_temp = os.path.join(derivFolderTemp, filenamePrefix+'.json')
				json_output = json.dumps(file_attrbs, indent=4)
				
				with open(json_file_temp, 'w') as (fid):
					fid.write(json_output)
					fid.write('\n')
				
				shutil.copy2(self.ref_template, os.path.join(spaceDataDir, os.path.basename(self.ref_template)))
				
				file_attrbs = {}
				file_attrbs['file_name'] = os.path.basename(self.ref_template)
				file_attrbs['node_name'] = os.path.basename(self.ref_template).split('nii')[0]
				file_attrbs['window'] = 9370.0
				file_attrbs['level'] = 4700.0
				file_attrbs['coregistered'] = False
				file_attrbs['vol_type'] = 'template'
				file_attrbs['reference'] = 'n/a'
				json_file_temp = os.path.join(spaceDataDir, file_attrbs['file_name'].split('.nii')[0] + '.json')
				json_output = json.dumps(file_attrbs, indent=4)
				with open(json_file_temp, 'w') as (fid):
					fid.write(json_output)
					fid.write('\n')
		
		shutil.rmtree(tempDir)
		self.addLog('Registration is completed')

	def getVTKMatrixFromNumpyMatrix(self,numpyMatrix):
		dimensions = len(numpyMatrix) - 1
		if dimensions == 2:
			vtkMatrix = vtk.vtkMatrix3x3()
		elif dimensions == 3:
			vtkMatrix = vtk.vtkMatrix4x4()
		else:
			raise ValueError('Unknown matrix dimensions.')
		for row in range(dimensions + 1):
			for col in range(dimensions + 1):
				vtkMatrix.SetElement(row, col, numpyMatrix[(row, col)])
		return vtkMatrix

	def readRegMatrix(self, trsfPath):
		with open(trsfPath) as (f):
			return np.loadtxt(f.readlines())

#
# registrationTest
#

class registrationTest(ScriptedLoadableModuleTest):
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
		self.test_registration1()

	def test_registration1(self):
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
		inputVolume = SampleData.downloadSample('registration1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = registrationLogic()

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


class CompareVolumesLogic:

	def __init__(self):
			
		self.sliceViewItemPattern = """
		<item><view class="vtkMRMLSliceNode" singletontag="{viewName}">
		  <property name="orientation" action="default">{orientation}</property>
		  <property name="viewlabel" action="default">{viewName}</property>
		  <property name="viewcolor" action="default">{color}</property>
		</view></item>
		"""
		self.colors = slicer.util.getNode('GenericColors')
		self.lookupTable = self.colors.GetLookupTable()
		self.firstCompare = False

	def assignLayoutDescription(self, layoutDescription):
		"""
		assign the xml to the user-defined layout slot

		"""
		layoutNode = slicer.util.getNode('*LayoutNode*')
		if layoutNode.IsLayoutDescription(layoutNode.SlicerLayoutUserView):
			layoutNode.SetLayoutDescription(layoutNode.SlicerLayoutUserView, layoutDescription)
		else:
			layoutNode.AddLayoutDescription(layoutNode.SlicerLayoutUserView, layoutDescription)
		layoutNode.SetViewArrangement(layoutNode.SlicerLayoutUserView)

	def viewersPerVolume(self, volumeNodes=None, background=None, label=None,opacity=0.5):
		orientations = {
			'Red':'Axial', 
			'Yellow':'Sagittal', 
			'Green':'Coronal'
		}
		index = 1
		layoutDescription = ''
		layoutDescription += '<layout type="vertical">\n'

		for volumeNode in volumeNodes:
			layoutDescription += ' <item> <layout type="horizontal">\n'
			column = 0
			for sliceColor, orientation in orientations.items():
				rgb = [int(round(v * 255)) for v in self.lookupTable.GetTableValue(index)[:-1]]
				color = '#%0.2X%0.2X%0.2X' % tuple(rgb)
				layoutDescription += self.sliceViewItemPattern.format(viewName=sliceColor, orientation=orientation, color=color)
				index += 1
				column += 1

			layoutDescription += '</layout></item>\n'

		layoutDescription += '</layout>'
		self.assignLayoutDescription(layoutDescription)
		
		slicer.app.processEvents()
		
		layoutManager = slicer.app.layoutManager()
		for volumeNode in volumeNodes:
			for sliceColor, orientation in orientations.items():
				sliceWidget = layoutManager.sliceWidget(sliceColor)
				compositeNode = sliceWidget.mrmlSliceCompositeNode()
				compositeNode.SetBackgroundVolumeID(background.GetID())
				compositeNode.SetForegroundVolumeID(volumeNode.GetID())
				compositeNode.SetForegroundOpacity(opacity)
				sliceNode = sliceWidget.mrmlSliceNode()
				sliceNode.SetOrientation(orientation)
				if self.firstCompare:
					sliceWidget.fitSliceToBackground()
				sliceWidget.sliceController().barWidget().children()[1].setChecked(True)
				sliceWidget.sliceController().children()[3].findChildren('ctkExpandButton')[0].setChecked(True)


class ViewWatcher(object):
	__doc__ = 'A helper class to manage observers on slice views'

	def __init__(self):
		self.currentLayoutName = None
		self.priority = 2
		self.observerTags = []
		self.sliceWidgetsPerStyle = {}
		self.refreshObservers()
		self.savedCursor = None
		layoutManager = slicer.app.layoutManager()
		layoutManager.connect('layoutChanged(int)', self.refreshObservers)
		self.sliceWidget = None
		self.sliceView = None
		self.sliceLogic = None
		self.sliceNode = None
		self.interactor = None
		self.xy = (0, 0)
		self.xyz = (0, 0, 0)
		self.ras = (0, 0, 0)
		self.layerLogics = {}
		self.layerVolumeNodes = {}
		self.savedWidget = None

	def cleanup(self):
		"""Virtual method meant to be overridden by the subclass
		Cleans up any observers (or widgets and other instances).
		This is needed because __del__ does not reliably get called.
		"""
		layoutManager = slicer.app.layoutManager()
		layoutManager.disconnect('layoutChanged(int)', self.refreshObservers)
		self.removeObservers()

	def removeObservers(self):
		for observee, tag in self.observerTags:
			observee.RemoveObserver(tag)

		self.observerTags = []
		self.sliceWidgetsPerStyle = {}

	def refreshObservers(self):
		"""
		When the layout changes, drop the observers from
		all the old widgets and create new observers for the
		newly created widgets
		"""
		self.removeObservers()
		layoutManager = slicer.app.layoutManager()
		sliceNodeCount = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLSliceNode')
		for nodeIndex in range(sliceNodeCount):
			sliceNode = slicer.mrmlScene.GetNthNodeByClass(nodeIndex, 'vtkMRMLSliceNode')
			sliceWidget = layoutManager.sliceWidget(sliceNode.GetLayoutName())
			if sliceWidget:
				style = sliceWidget.sliceView().interactorStyle().GetInteractor()
				self.sliceWidgetsPerStyle[style] = sliceWidget
				events = ('MouseMoveEvent', 'EnterEvent', 'LeaveEvent')
				for event in events:
					tag = style.AddObserver(event, self.processEvent, self.priority)
					self.observerTags.append([style, tag])

				tag = sliceNode.AddObserver('ModifiedEvent', self.processEvent, self.priority)
				self.observerTags.append([sliceNode, tag])
				sliceLogic = sliceWidget.sliceLogic()
				compositeNode = sliceLogic.GetSliceCompositeNode()
				tag = compositeNode.AddObserver('ModifiedEvent', self.processEvent, self.priority)
				self.observerTags.append([compositeNode, tag])

	def processEvent(self, observee, event):
		if event == 'LeaveEvent':
			self.currentLayoutName = None

		if event == 'EnterEvent':
			sliceWidget = self.sliceWidgetsPerStyle[observee]
			self.currentLayoutName = None
			sliceLogic = sliceWidget.sliceLogic()
			sliceNode = sliceWidget.mrmlSliceNode()
			self.currentLayoutName = sliceNode.GetLayoutName()
		
		nodeEvent = observee.IsA('vtkMRMLSliceNode') or observee.IsA('vtkMRMLSliceCompositeNode')
		
		if nodeEvent:
			layoutManager = slicer.app.layoutManager()
			sliceWidget = layoutManager.sliceWidget(observee.GetLayoutName())
			if sliceWidget:
				if observee.GetLayoutName() == self.currentLayoutName:
					observee = sliceWidget.sliceView().interactor()
		
		if observee in self.sliceWidgetsPerStyle:
			self.sliceWidget = self.sliceWidgetsPerStyle[observee]
			self.sliceView = self.sliceWidget.sliceView()
			self.sliceLogic = self.sliceWidget.sliceLogic()
			self.sliceNode = self.sliceWidget.mrmlSliceNode()
			self.interactor = observee
			self.xy = self.interactor.GetEventPosition()
			self.xyz = self.sliceWidget.sliceView().convertDeviceToXYZ(self.xy)
			self.ras = self.sliceWidget.sliceView().convertXYZToRAS(self.xyz)
			
			self.layerLogics = {}
			self.layerVolumeNodes = {}
			layerLogicCalls = (
				('L', self.sliceLogic.GetLabelLayer),
				('F', self.sliceLogic.GetForegroundLayer),
				('B', self.sliceLogic.GetBackgroundLayer)
			)
			for layer, logicCall in layerLogicCalls:
				self.layerLogics[layer] = logicCall()
				self.layerVolumeNodes[layer] = self.layerLogics[layer].GetVolumeNode()

			self.onSliceWidgetEvent(event)

	def onSliceWidgetEvent(self, event):
		"""
		Virtual method called when an event occurs
		on a slice widget.  The instance variables of the class
		will have been filled by the processEvent method above
		"""
		pass

	def tearDown(self):
		"""Virtual method meant to be overridden by the subclass
		Cleans up any observers (or widgets and other instances).
		This is needed because __del__ does not reliably get called.
		"""
		layoutManager = slicer.app.layoutManager()
		layoutManager.disconnect('layoutChanged(int)', self.refreshObservers)
		self.removeObservers()

	def cursorOff(self, widget):
		"""
		Turn off and save the current cursor so
		the user can see an overlay that tracks the mouse
		"""
		if self.savedWidget == widget:
			return
		self.cursorOn()
		self.savedWidget = widget
		self.savedCursor = widget.cursor
		qt_BlankCursor = 10
		widget.setCursor(qt.QCursor(qt_BlankCursor))

	def cursorOn(self):
		"""
		Restore the saved cursor if it exists, otherwise
		just restore the default cursor
		"""
		if self.savedWidget:
			if self.savedCursor:
				self.savedWidget.setCursor(self.savedCursor)
			else:
				self.savedWidget.unsetCursor()
		self.savedWidget = None
		self.savedCursor = None


class LayerReveal(ViewWatcher):
	__doc__ = 'Track the mouse and show a reveal view'

	def __init__(self, parent=None, width=400, height=400, showWidget=False, scale=False):
		super().__init__()
		self.width = width
		self.height = height
		self.showWidget = showWidget
		self.scale = scale
		self.renderer = None
		self.gray = qt.QColor()
		self.gray.setRedF(0.5)
		self.gray.setGreenF(0.5)
		self.gray.setBlueF(0.5)
		self.painter = qt.QPainter()
		
		if self.showWidget:
			self.frame = qt.QFrame(parent)
			mw = slicer.util.mainWindow()
			self.frame.setGeometry(mw.x, mw.y, self.width, self.height)
			self.frameLayout = qt.QVBoxLayout(self.frame)
			self.label = qt.QLabel()
			self.frameLayout.addWidget(self.label)
			self.frame.show()

		self.vtkImage = vtk.vtkImageData()
		self.mrmlUtils = slicer.qMRMLUtils()
		self.imageMapper = vtk.vtkImageMapper()
		self.imageMapper.SetColorLevel(128)
		self.imageMapper.SetColorWindow(255)
		self.imageMapper.SetInputData(self.vtkImage)
		self.actor2D = vtk.vtkActor2D()
		self.actor2D.SetMapper(self.imageMapper)

	def cleanup(self):
		self.frame = None
		if self.renderer:
			self.renderer.RemoveActor(self.actor2D)
		
		self.cursorOn()
		
		if self.sliceView:
			self.sliceView.scheduleRender()
		
		try:
			super().cleanup()
		except TypeError:
			pass

	def onSliceWidgetEvent(self, event):
		"""
		Update reveal displays
		"""
		revealPixmap = self.revealPixmap(self.xy)
		
		if self.showWidget:
			self.label.setPixmap(revealPixmap)
		
		self.renderWindow = self.sliceView.renderWindow()
		self.renderer = self.renderWindow.GetRenderers().GetItemAsObject(0)
		
		if event == 'LeaveEvent' or not self.layerVolumeNodes['F']:
			self.renderer.RemoveActor(self.actor2D)
			self.cursorOn()
			self.sliceView.forceRender()
		elif event == 'EnterEvent':
			self.renderer.AddActor2D(self.actor2D)
			if self.layerVolumeNodes['F'] and (self.layerVolumeNodes['F'] != self.layerVolumeNodes['B']):
				self.cursorOff(self.sliceWidget)
		else:
			self.mrmlUtils.qImageToVtkImageData(revealPixmap.toImage(), self.vtkImage)
			self.imageMapper.SetInputData(self.vtkImage)
			x, y = self.xy
			self.actor2D.SetPosition(x - self.width // 2, y - self.height // 2)
			self.sliceView.forceRender()

	def revealPixmap(self, xy):
		"""
		fill a pixmap with an image that has a reveal pattern
		at xy with the fg drawn over the bg
		"""
		bgVTKImage = self.layerLogics['B'].GetImageData()
		fgVTKImage = self.layerLogics['F'].GetImageData()
		bgQImage = qt.QImage()
		fgQImage = qt.QImage()
		slicer.qMRMLUtils().vtkImageDataToQImage(bgVTKImage, bgQImage)
		slicer.qMRMLUtils().vtkImageDataToQImage(fgVTKImage, fgQImage)
		
		imageWidth = bgQImage.width()
		imageHeight = bgQImage.height()
		x, y = xy
		yy = imageHeight - y
		
		overlayImage = qt.QImage(imageWidth, imageHeight, qt.QImage().Format_ARGB32)
		overlayImage.fill(0)
		
		halfWidth = imageWidth // 2
		halfHeight = imageHeight // 2
		topLeft = qt.QRect(0, 0, x, yy)
		bottomRight = qt.QRect(x, yy, imageWidth - x - 1, imageHeight - yy - 1)
		
		self.painter.begin(overlayImage)
		self.painter.drawImage(topLeft, fgQImage, topLeft)
		self.painter.drawImage(bottomRight, fgQImage, bottomRight)
		self.painter.end()
		
		compositePixmap = qt.QPixmap(self.width, self.height)
		compositePixmap.fill(self.gray)
		self.painter.begin(compositePixmap)
		self.painter.drawImage(-1 * (x - self.width // 2), -1 * (yy - self.height // 2), bgQImage)
		self.painter.drawImage(-1 * (x - self.width // 2), -1 * (yy - self.height // 2), overlayImage)
		self.painter.end()
		
		if self.scale:
			compositePixmap = self.scalePixmap(compositePixmap)
		
		self.painter.begin(compositePixmap)
		self.pen = qt.QPen()
		self.color = qt.QColor('#FF0')
		self.color.setAlphaF(0.3)
		self.pen.setColor(self.color)
		self.pen.setWidth(5)
		self.pen.setStyle(3)
		self.painter.setPen(self.pen)
		rect = qt.QRect(1, 1, self.width - 2, self.height - 2)
		self.painter.drawRect(rect)
		self.painter.end()
		
		return compositePixmap

	def scalePixmap(self, pixmap):
		halfWidth = self.width // 2
		halfHeight = self.height // 2
		quarterWidth = self.width // 4
		quarterHeight = self.height // 4
		centerPixmap = qt.QPixmap(halfWidth, halfHeight)
		centerPixmap.fill(self.gray)
		self.painter.begin(centerPixmap)
		fullRect = qt.QRect(0, 0, halfWidth, halfHeight)
		centerRect = qt.QRect(quarterWidth, quarterHeight, halfWidth, halfHeight)
		self.painter.drawPixmap(fullRect, pixmap, centerRect)
		self.painter.end()
		scaledPixmap = centerPixmap.scaled(self.width, self.height)
		return scaledPixmap
