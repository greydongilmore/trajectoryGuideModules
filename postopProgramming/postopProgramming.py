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

from helpers.helpers import warningBox, VTAModelBuilderClass, dotdict, getMarkupsNode, getPointCoords, addCustomLayouts, createElecBox, imagePopup
from helpers.variables import electrodeModels,groupboxStyle, slicerLayout, module_dictionary

#
# postopProgramming
#

class postopProgramming(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "08: Postop Programming"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = []
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#postopProgramming">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# postopProgrammingWidget
#

class postopProgrammingWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
		
		self.elecModel = None
		self.elecModelLastButton = None
		self.elecModelButton = 0
		self.elecChanLastButton = None
		self.elecChanButton = 0
		self.lastPolButton=0
		self.active = False

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
		self.logic = postopProgrammingLogic()

		# Connections
		self._setupConnections()

	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/postopProgramming.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)

		#self.polarityButtonGroups = [
		#	self.ui.polarity01,
		#	self.ui.polarity02,
		#	self.ui.polarity03,
		#	self.ui.polarity04,
		#	self.ui.polarity05,
		#	self.ui.polarity06,
		#	self.ui.polarity07,
		#	self.ui.polarity08
		#]

		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
		self.ui.planNameGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.electrodeChannelGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.electrodeModelGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.stimSettingsGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.vtaAlgoGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')


		self.ui.postElecCB.addItems(['Select Electrode']+list(electrodeModels))
		
	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		
		self.ui.moduleSelectCB.connect('currentIndexChanged(int)', self.onModuleSelectorCB)

		self.ui.planAdd.connect('clicked(bool)', self.onPlanAdd)
		self.ui.planDelete.connect('clicked(bool)', self.onPlanDelete)
		self.ui.planAddConfirm.connect('clicked(bool)', self.onPlanAddConfirm)
		self.ui.planNameEdit.connect('returnPressed()', self.ui.planAddConfirm.click)

		self.ui.planNameEdit.connect('returnPressed()', self.ui.planAddConfirm.click)

		self.ui.planName.connect('currentIndexChanged(int)', self.onPlanChange)
		self.ui.planAddConfirm.setVisible(0)
		not_resize = self.ui.planAddConfirm.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planAddConfirm.setSizePolicy(not_resize)
		self.ui.planNameEdit.setVisible(0)
		
		self.ui.showVTAButton.clicked.connect(self.onVTAModelButton)
		self.ui.clearTableButton.clicked.connect(self.clearTable)
		self.ui.postElecCB.currentIndexChanged.connect(lambda: self.onButtonClick(self.ui.postElecCB))
		self.ui.electrodeChannelButtonGroup.buttonClicked.connect(self.onButtonClick)
		self.ui.electrodeShowDiagram.clicked.connect(self.onElectrodeShowDiagram)
		
		# Make sure parameter node is initialized (needed for module reload)
		self.initializeParameterNode()

		self.logic.addCustomLayouts()

	def cleanup(self):
		"""
		Called when the application closes and the module widget is destroyed.
		"""
		self.removeObservers()
		self.active = False

	def enter(self):
		"""
		Called each time the user opens this module.
		"""
		# Make sure parameter node exists and observed
		self.initializeParameterNode()
		self.active = True
		self.onPlanChange()

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

		moduleIndex = [i for i,x in enumerate(list(module_dictionary.values())) if x == slicer.util.moduleSelector().selectedModule][0]
		self.ui.moduleSelectCB.setCurrentIndex(self.ui.moduleSelectCB.findText(list(module_dictionary)[moduleIndex]))
		
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

		if self._parameterNode is None or self._updatingGUIFromParameterNode and not self.active:
			return

		# Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
		self._updatingGUIFromParameterNode = True

		if self._parameterNode.GetParameter('derivFolder'):

			planNames = [self.ui.planName.itemText(i) for i in range(self.ui.planName.count)]

			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as surgical_info:
				surgical_info_json = json.load(surgical_info)

			plansAdd = [x for x in list(surgical_info_json['trajectories']) if x not in planNames]
			if plansAdd:
				self.ui.planName.blockSignals(True)
				self.ui.planName.addItems(plansAdd)
				self.ui.planName.blockSignals(False)
				
				self.onPlanChange()

		# All the GUI updates are done
		self._updatingGUIFromParameterNode = False

	def updateParameterNodeFromGUI(self, caller=None, event=None):
		"""
		This method is called when the user makes any change in the GUI.
		The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
		"""

		if self._parameterNode is None or self._updatingGUIFromParameterNode and not self.active:
			return

		#wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch
		#self._parameterNode.EndModify(wasModified)

	def onModuleSelectorCB(self, moduleIndex):
		moduleName = module_dictionary[self.ui.moduleSelectCB.itemText(moduleIndex)]
		currentModule = slicer.util.moduleSelector().selectedModule
		if currentModule != moduleName:
			slicer.util.moduleSelector().selectModule(moduleName)

	def onButtonClick(self, button):
		if isinstance(button,tuple):
			buttonName = button[0]
			buttonText = button[1]
		elif button.name == 'postElecCB':
			buttonName = button.name
			buttonText = self.ui.postElecCB.currentText
		else:
			buttonName = button.name
			buttonText = button.text

		if 'postElecCB' in buttonName:

			self.elecNumber = []
			children = self.ui.electrodeChannelGB.findChildren('QCheckBox')
			for i in children:
				if i.isChecked():
					self.elecNumber = 'electrode_' + i.text
			
			if not self.elecNumber:
				pass
	# 			warningBox("Please select electrode number.")
			else:
				if self.ui.postElecCB.currentText != 'Select Electrode':
					self.clearTable()
					self.elecModel = self.ui.postElecCB.currentText
					self.elspec = electrodeModels[self.elecModel]
					
					elecWig_dict={}
					for icon in range(self.elspec['num_contacts']):
						elecWig_dict[icon+1]=createElecBox(icon+1, self.elspec['contact_label'][icon]+str(self.elspec[self.elecNumber][icon]))

					new_elecs = self.uiWidget.findChild(qt.QWidget,'new_elecs')
					elecGridLayout = self.uiWidget.findChild(qt.QWidget,'new_elecs').layout()
					
					while elecGridLayout.count():
						child = elecGridLayout.takeAt(0)
						if child.widget():
							child.widget().deleteLater()

					
					titleLine = qt.QFrame()
					titleLine.setFrameShape(qt.QFrame.HLine)
					titleLine.setFixedWidth(290)

					botLine = qt.QFrame()
					botLine.setFrameShape(qt.QFrame.HLine)
					botLine.setFixedWidth(420)

					spaceItem = qt.QLabel('')
					spaceItem.setFixedWidth(60)
					spaceItem.setAlignment(qt.Qt.AlignLeft)

					fontSettings = qt.QFont("font-size: 11pt;font-family: Arial")
					fontSettings.setBold(True)

					ampLabel = qt.QLabel('Amp')
					ampLabel.setFont(fontSettings)
					ampLabel.setFixedWidth(70)
					ampLabel.setAlignment(qt.Qt.AlignLeft)

					freqLabel = qt.QLabel('Freq')
					freqLabel.setFont(fontSettings)
					freqLabel.setFixedWidth(70)
					freqLabel.setAlignment(qt.Qt.AlignLeft)

					pwLabel = qt.QLabel('PW')
					pwLabel.setFont(fontSettings)
					pwLabel.setFixedWidth(70)
					pwLabel.setAlignment(qt.Qt.AlignLeft)

					impLabel = qt.QLabel('Imp')
					impLabel.setFont(fontSettings)
					impLabel.setFixedWidth(75)
					impLabel.setAlignment(qt.Qt.AlignLeft)

					headGridLayout = qt.QGridLayout()
					headGridLayout.addWidget(spaceItem,0,0,2,2)
					headGridLayout.addWidget(titleLine,0,1,1,4)
					headGridLayout.addWidget(ampLabel,1,1,1,1)
					headGridLayout.addWidget(freqLabel,1,2,1,1)
					headGridLayout.addWidget(pwLabel,1,3,1,1)
					headGridLayout.addWidget(impLabel,1,4,1,1)
					headGridLayout.addWidget(botLine,2,0,1,5)

					headWig = qt.QWidget()
					headWig.setLayout(headGridLayout)

					elecGridLayout.addWidget(headWig,0,1)

					polarityButtonGroup_dict={}
					cnt=1
					bntCnt=0
					for ielec in list(elecWig_dict):
						elecGridLayout.addWidget(elecWig_dict[ielec],cnt,1)
						cnt += 1

		elif 'elecNumber' in buttonName:

			children = self.ui.electrodeChannelGB.findChildren('QCheckBox')
			for i in children:
				i.setChecked(False)

			cnt=0
			for i in children:
				if i.text == buttonText:
					self.elecChanButton=cnt
				cnt+=1

			if np.all([children[self.elecChanButton].isChecked(), self.elecChanButton == self.elecChanLastButton]):
				children[self.elecChanButton].setChecked(True)
				self.elecChanLastButton = self.elecChanButton
			elif np.all([children[self.elecChanButton].isChecked()==False, self.elecChanButton != self.elecChanLastButton]):
				children[self.elecChanButton].setChecked(True)
				self.elecChanLastButton = self.elecChanButton

			self.elecNumber = []
			children = self.ui.electrodeChannelGB.findChildren('QCheckBox')
			for i in children:
				if i.isChecked():
					self.elecNumber = 'electrode_' + i.text

			if self.elecNumber:
				button_send=None
				if self.ui.postElecCB.currentText != 'Select Electrode':
					button_send = dotdict({'name':'postElecCB'})

				if button_send is not None:
					self.onButtonClick(button_send)

	def clearTable(self):
		for ibutton in self.ui.stimSettingsGB.findChildren('QCheckBox'):
			ibutton.setChecked(False)

		children = self.ui.stimSettingsGB.findChildren('QWidget')
		for i in children:
			spinbox = i.findChildren('QDoubleSpinBox')
			for ispin in spinbox:
				ispin.value = 0

	def resetValues(self):
		
		self.clearTable()

		children = self.ui.electrodeChannelGB.findChildren('QCheckBox')
		for i in children:
			i.checked = False

		self.ui.postElecCB.setCurrentIndex(self.ui.postElecCB.findText('Select Electrode'))

		children = self.ui.vtaAlgoGB.findChildren('QRadioButton')
		for i in children:
			i.checked = False

		self.elecModelLastButton = None
		self.elecModelButton = 0
		self.elecChanLastButton = None
		self.elecChanButton = 0

	def onPlanAdd(self):
		if not self.ui.planNameEdit.isVisible():
			self.ui.planNameEdit.setVisible(1)
			self.ui.planAddConfirm.setVisible(1)

	def onPlanAddConfirm(self):
		if self.ui.planNameEdit.text == '':
			warningBox('Pleae enter a plan name!')
			return
		elif self.ui.planNameEdit.text == 'Select Plan':
			warningBox('Pleae select a name!')
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

	def onPlanDelete(self):
		if self.ui.planName.currentText == '' or self.ui.planName.currentText == 'Select plan':
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

			planName = self.ui.planName.currentText
			self.ui.planName.removeItem(self.ui.planName.findText(planName))

			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
				surgical_data = json.load(surg_file)
			
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

			lineNode = getMarkupsNode(planName + '_line-post', 'vtkMRMLMarkupsLineNode')
			if lineNode is not None:
				slicer.mrmlScene.RemoveNode(lineNode)
			
			fidNode = getMarkupsNode(planName + '_fiducials', 'vtkMRMLMarkupsFiducialNode')
			if fidNode is not None:
				slicer.mrmlScene.RemoveNode(fidNode)

	def onPlanChange(self):
		if self.active and self._parameterNode.GetParameter('derivFolder'):
			if self.ui.planName.currentText != '' or self.ui.planName.currentText != 'Select Plan':
				
				planName = self.ui.planName.currentText
				self.resetValues()

				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
					surgical_data = json.load(surg_file)
				
				if planName in list(surgical_data['trajectories']):

					if 'elecUsed' in list(surgical_data['trajectories'][planName]["pre"]):
						if surgical_data['trajectories'][planName]["pre"]['elecUsed']:
								self.ui.postElecCB.setCurrentIndex(self.ui.postElecCB.findText(surgical_data['trajectories'][planName]['pre']['elecUsed']))
								self.elecModel = self.ui.postElecCB.currentText
					
					if 'programming' in list(surgical_data['trajectories'][planName]):
						if 'elecNumber' in list(surgical_data['trajectories'][planName]['programming']):
							if surgical_data['trajectories'][planName]['programming']['elecNumber']!=0:
									children = self.ui.electrodeChannelGB.findChildren('QCheckBox')
									for i in children:
										if i.text == str(surgical_data['trajectories'][planName]['programming']['elecNumber']):
											i.checked = True
											self.elecNumber = int(i.text)
											self.onButtonClick(('elecNumber',i.text))
						
						if 'contact_info' in list(surgical_data['trajectories'][planName]['programming']):
							if surgical_data['trajectories'][planName]['programming']['contact_info']:
								for key, val in surgical_data['trajectories'][planName]['programming']['contact_info'].items():
									if val['perc'] > 0:
										self.uiWidget.findChild(qt.QDoubleSpinBox, f"contact0{val['boxNum']}Amp").setValue(val['amp'])
										self.uiWidget.findChild(qt.QDoubleSpinBox, f"contact0{val['boxNum']}Freq").setValue(val['freq'])
										self.uiWidget.findChild(qt.QDoubleSpinBox, f"contact0{val['boxNum']}PW").setValue(val['pw'])
										self.uiWidget.findChild(qt.QDoubleSpinBox, f"contact0{val['boxNum']}Imp").setValue(val['imp'])

										self.uiWidget.findChild(qt.QCheckBox, f"contact0{val['boxNum']}Neg").setChecked(val['neg'])
										self.uiWidget.findChild(qt.QCheckBox, f"contact0{val['boxNum']}Pos").setChecked(val['pos'])
					
					models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
					for imodel in models:
						if planName in imodel.GetName() and '_vta' in imodel.GetName():
							imodel.GetDisplayNode().SetVisibility(1)

	def onElectrodeShowDiagram(self):
		"""
		Slot for ``Electrode Diagram`` button belonging to ``Left Electrode``
		
		"""
		self.elecModelShow = []
		if self.ui.postElecCB.currentText != 'Select Electrode':
			self.elecModelShow = electrodeModels[self.ui.postElecCB.currentText]['filename']

		if not self.elecModelShow:
			self.elecModelShow = 'allElectrodes'
		
		parent = None
		for w in slicer.app.topLevelWidgets():
			if hasattr(w,'objectName'):
				if w.objectName == 'qSlicerMainWindow':
					parent=w
		
		imagePopup(self.elecModelShow + ' electrode', os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'static', self.elecModelShow + '.png'),parent)

	def get_contact_coords(self, side):
		DirVec = [side['entry'][0] - side['target'][0], side['entry'][1] - side['target'][1], side['entry'][2] - side['target'][2]]
		MagVec = np.sqrt([np.square(DirVec[0]) + np.square(DirVec[1]) + np.square(DirVec[2])])
		NormVec = np.array([float(DirVec[0] / MagVec), float(DirVec[1] / MagVec), float(DirVec[2] / MagVec)])
		index = [i for i, x in enumerate(electrodeModels.keys()) if side['elecUsed'] == x][0]
		e_specs = electrodeModels[list(electrodeModels)[index]]
		bottomTop = np.empty([0, 6])
		start = e_specs['encapsultation']
		conSize = e_specs['contact_size']
		conSpace = e_specs['contact_spacing']
		midContact = []
		for iContact in range(0, e_specs['num_contacts']):
			bottomTop = np.append(bottomTop, (np.hstack((
					np.array([[side['target'][0] + NormVec[0] * start],[side['target'][1] + NormVec[1] * start], [side['target'][2] + NormVec[2] * start]]).T,
					np.array(([side['target'][0] + NormVec[0] * (start + conSize)], [side['target'][1] + NormVec[1] * (start + conSize)], [side['target'][2] + NormVec[2] * (start + conSize)])).T
					))),
					axis=0
				)

			midContact.append(bottomTop[iContact, :3] + (bottomTop[iContact, 3:] - bottomTop[iContact, :3]) / 2)
			
			if np.all([side['elecUsed'].lower() in ('directional', 'bsci_directional', 'b.sci. directional'), 3 > iContact > 0]):
				midContact.append(bottomTop[iContact, :3] + (bottomTop[iContact, 3:] - bottomTop[iContact, :3]) / 2)
				midContact.append(bottomTop[iContact, :3] + (bottomTop[iContact, 3:] - bottomTop[iContact, :3]) / 2)
			
			start += conSize
			start += conSpace

		return midContact

	def onVTAModelButton(self):
		
		self.elecModel = self.ui.postElecCB.currentText

		if self.elecModel == 'Select Electrode' :
			warningBox(f'Please select electrode for {self.ui.planName.currentText}.')
			return

		contactRange = range(1, electrodeModels[self.elecModel]['num_contacts']+1)

		contact_info = {}
		for icontact in contactRange:
			contact_info[icontact-1] = {
				'label': self.ui.stimSettingsGB.findChild(qt.QLabel, f'contact{str(icontact).zfill(2)}Text').text,
				'perc': 100 if self.ui.stimSettingsGB.findChild(qt.QDoubleSpinBox, f'contact{str(icontact).zfill(2)}Amp').value > 0 else 0,
				'amp': self.ui.stimSettingsGB.findChild(qt.QDoubleSpinBox, f'contact{str(icontact).zfill(2)}Amp').value,
				'freq': self.ui.stimSettingsGB.findChild(qt.QDoubleSpinBox, f'contact{str(icontact).zfill(2)}Freq').value,
				'pw': self.ui.stimSettingsGB.findChild(qt.QDoubleSpinBox, f'contact{str(icontact).zfill(2)}PW').value,
				'imp': self.ui.stimSettingsGB.findChild(qt.QDoubleSpinBox, f'contact{str(icontact).zfill(2)}Imp').value,
				'neg': self.ui.stimSettingsGB.findChild(qt.QCheckBox, f'contact{str(icontact).zfill(2)}Neg').isChecked(),
				'pos': self.ui.stimSettingsGB.findChild(qt.QCheckBox, f'contact{str(icontact).zfill(2)}Pos').isChecked(),
				'boxNum':icontact
			 }

		self.vtaAlgorithm = []
		children = self.ui.vtaAlgoGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked():
				self.vtaAlgorithm = i.text

		self.elecNumber = []
		children = self.ui.electrodeChannelGB.findChildren('QCheckBox')
		for i in children:
			if i.isChecked():
				self.elecNumber = int(i.text)

		side_data = {
 			'elecUsed': self.elecModel,
 			'elecNumber': self.elecNumber, 
 			'VTA_algo': self.vtaAlgorithm,
 			'contact_info': contact_info
		}

		if self._parameterNode.GetParameter('derivFolder'):
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surgical_file):
				surgical_data = json.load(surgical_file)

			surgical_data['trajectories'][self.ui.planName.currentText]['programming'] = side_data

			json_output = json.dumps(surgical_data, indent=4)
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json"), 'w') as (fid):
				fid.write(json_output)
				fid.write('\n')

			side_data['side']=surgical_data['trajectories'][self.ui.planName.currentText]['side']
			mcpCoords = getPointCoords('acpc', 'mcp')
			side_data['entry'] = surgical_data['trajectories'][self.ui.planName.currentText]['post']['entry'].copy()
			side_data['target'] = surgical_data['trajectories'][self.ui.planName.currentText]['post']['target'].copy()
			side_data['data_dir'] = os.path.join(self._parameterNode.GetParameter('derivFolder'))
			side_data['output_name'] = f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-post_task-{self.ui.planName.currentText}_vta.vtk"

			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'settings', 'model_visibility.json')) as (settings_file):
				slice_vis = json.load(settings_file)
			
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'settings', 'model_color.json')) as (settings_file):
				model_colors = json.load(settings_file)
		else:
			side_data['side']='right'
			side_data['entry'] = [10,10,10]
			side_data['target'] = [0,0,0]
			side_data['nodeName'] = f"ses-post_task-{self.ui.planName.currentText}_vta"

			with open(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'settings', 'model_visibility.json')) as (settings_file):
				slice_vis = json.load(settings_file)
			
			with open(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'settings', 'model_color.json')) as (settings_file):
				model_colors = json.load(settings_file)
			
		side_data['model_col'] = model_colors['actualVTAColor']
		side_data['model_vis'] = slice_vis['actualVTA3DVis']
		
		side_data['plan_name'] = self.ui.planName.currentText
		side_data['coords'] = self.get_contact_coords(side_data)
		
		
		VTAModelBuilder = VTAModelBuilderClass(side_data)
		
		mniTransform = [x for x in slicer.util.getNodesByClass('vtkMRMLLinearTransformNode') if 'finalMNI' in x.GetName()]
		if mniTransform:
			model = slicer.util.getNode(side_data['side'] + '_actual_vta_model*')
			model.SetAndObserveTransformNodeID(mniTransform[0].GetID())

#
# postopProgrammingLogic
#

class postopProgrammingLogic(ScriptedLoadableModuleLogic):
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
		self.postopProgrammingInstance = None
		self.FrameAutoDetect = False

	def getParameterNode(self, replace=False):
		"""Get the postopProgramming parameter node.

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
		""" Create the postopProgramming parameter node.

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



#
# postopProgrammingTest
#

class postopProgrammingTest(ScriptedLoadableModuleTest):
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
		self.test_postopProgramming1()

	def test_postopProgramming1(self):
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
		inputVolume = SampleData.downloadSample('postopProgramming1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = postopProgrammingLogic()

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
