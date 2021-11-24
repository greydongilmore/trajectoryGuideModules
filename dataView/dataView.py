import os
import sys
import shutil
import numpy as np
import json
import glob
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

if getattr(sys, 'frozen', False):
	cwd = os.path.dirname(sys.argv[0])
elif __file__:
	cwd = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.dirname(cwd))

from helpers.helpers import vtkModelBuilderClass, getReverseTransform, hex2rgb, rgbToHex,\
createModelBox, sorted_nicely, addCustomLayouts, sortSceneData
from helpers.variables import coordSys, slicerLayout, groupboxStyle, ctkCollapsibleGroupBoxStyle,\
ctkCollapsibleGroupBoxTitle, groupboxStyleTitle, fontSettingTitle, defaultTemplateSpace

#
# dataView
#

class dataView(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "dataView"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = []
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#dataView">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# dataViewWidget
#

class dataViewWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
		self.templateModelNames = None
		self.modelColors=None
		self.active = False

	def setup(self):
		"""
		Called when the user opens the module the first time and the widget is initialized.
		"""
		ScriptedLoadableModuleWidget.setup(self)

		# Create logic class. Logic implements all computations that should be possible to run
		# in batch mode, without a graphical user interface.
		self.logic = dataViewLogic()

		self._loadUI()

		# Connections
		self._setupConnections()

	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/dataView.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)

		# Make sure parameter node is initialized (needed for module reload)
		self.initializeParameterNode()

		with open(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'settings', 'model_color.json')) as (settings_file):
			self.modelColors = json.load(settings_file)

		default_template_path = os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space')

		templateSpaces = [x.split('tpl-')[(-1)] for x in os.listdir(default_template_path) if os.path.isdir(os.path.join(default_template_path, x))]
		self.ui.templateSpaceCB.addItems(templateSpaces)
		self.ui.templateSpaceCB.setCurrentIndex(self.ui.templateSpaceCB.findText(defaultTemplateSpace))
		
		self.ui.plannedLeadVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['plannedLeadColor'])))
		self.ui.intraLeadVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['intraLeadColor'])))
		self.ui.actualLeadVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['actualLeadColor'])))
		self.ui.plannedContactVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['plannedContactColor'])))
		self.ui.intraContactVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['intraContactColor'])))
		self.ui.actualContactVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['actualContactColor'])))
		
		self.ui.intraMicroelectrodesVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['intraMicroelectrodesColor'])))
		self.ui.actualMicroelectrodesVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['actualMicroelectrodesColor'])))
		self.ui.intraMERActivityVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['intraMERActivityColor'])))
		self.ui.actualMERActivityVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['actualMERActivityColor'])))
		self.ui.actualVTAVisColor.setColor(qt.QColor(rgbToHex(self.modelColors['actualVTAColor'])))
		
		self.setupModelWigets()

		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
		fontSettings = qt.QFont(fontSettingTitle)
		fontSettings.setBold(True)
		self.ui.planModelsGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.planModelsGB.setFont(fontSettings)
		self.ui.VTAVisWig.setFont(fontSettings)
		self.ui.merActivityVisWig.setFont(fontSettings)
		self.ui.merTracksVisWig.setFont(fontSettings)
		self.ui.contactsVisWig.setFont(fontSettings)
		self.ui.leadVisWig.setFont(fontSettings)
		self.ui.plannedLeadVisWig.setFont(fontSettings)
		
		fontSettings = qt.QFont(groupboxStyleTitle)
		fontSettings.setBold(False)
		self.ui.templateModelsVisGB.setFont(fontSettings)
		self.ui.templateModelsVisGB.setStyleSheet(ctkCollapsibleGroupBoxStyle + f"color: {self.text_color}" + '}' + ctkCollapsibleGroupBoxTitle + f"color: {self.text_color}" + '}')
		self.ui.templateModelsVisGB.collapsed = 1

		self._dictRB={}
		children = self.ui.planModelsGB.findChildren('QRadioButton')
		for i in children:
			self._dictRB[i.name]=i.isChecked()

	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		
		self.ui.colorPickerButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onGroupButton)
		self.ui.patientModelsViewButtonGroup.buttonClicked.connect(self.onGroupButton)
		self.ui.planName.connect('currentIndexChanged(int)', self.onPlanChange)

		self.ui.plannedLeadOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.plannedLeadOpacity))
		self.ui.intraLeadOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.intraLeadOpacity))
		self.ui.actualLeadOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.actualLeadOpacity))
		self.ui.plannedContactOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.plannedContactOpacity))
		self.ui.intraContactOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.intraContactOpacity))
		self.ui.actualContactOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.actualContactOpacity))
		self.ui.plannedMicroelectrodesOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.plannedMicroelectrodesOpacity))
		self.ui.intraMicroelectrodesOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.intraMicroelectrodesOpacity))
		self.ui.actualMicroelectrodesOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.actualMicroelectrodesOpacity))
		self.ui.intraMERActivityOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.intraMERActivityOpacity))
		self.ui.actualMERActivityOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.actualMERActivityOpacity))
		self.ui.actualVTAOpacity.valueChanged.connect(lambda : self.onModelOpacityChange(self.ui.actualVTAOpacity))

		self.ui.allPatientModelsOpacity.valueChanged.connect(lambda : self.onAllModelOpacityChange(self.ui.allPatientModelsOpacity))
		self.ui.allTemplateModelsOpacity.valueChanged.connect(lambda : self.onAllModelOpacityChange(self.ui.allTemplateModelsOpacity))

		self.ui.templateSpaceCB.connect('currentIndexChanged(int)', self.setupModelWigets)
		self.ui.allModelsButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onAllModelsGroupButton)
		self.ui.templateViewButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onTemplateViewGroupButton)
		
		self.ui.sortSceneDataButton.clicked.connect(self.onSaveSceneButton)

		
		if self._parameterNode.GetParameter('derivFolder'):
			if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'),'space')):

				templateSpaces = [x.split('_to-')[-1].split('_xfm')[0] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'),'space')) if x.endswith('.h5')]
				self.ui.templateSpaceCB.clear()
				self.ui.templateSpaceCB.addItems(templateSpaces)

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
		self.onPlanChange()

	def exit(self):
		"""
		Called each time the user opens a different module.
		"""
		# Do not react to parameter node changes (GUI will be updated when the user enters into the module)
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
			self.ui.planName.addItems(plansAdd)

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

	def setupModelWigets(self):

		space = self.ui.templateSpaceCB.currentText

		if self.active and space != 'Select template':
		
			self.templateModelNames = np.unique([x.split('_desc-')[(-1)].split('.vtk')[0] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models')) if x.endswith('vtk')])
			
			with open(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models', 'template_model_colors.json')) as (settings_file):
				templateModelColors = json.load(settings_file)

			with open(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'template_model_dictionary.json')) as (name_file):
				templateModelNameDict= json.load(name_file)

			modelWig_dict={}
			for modelName in self.templateModelNames:
				modelWig_dict = createModelBox(modelName, templateModelNameDict, modelWig_dict)
			
			new_models = self.uiWidget.findChild(qt.QWidget,'new_models')
			modelGridLayout = self.uiWidget.findChild(qt.QWidget,'new_models').layout()
			
			while modelGridLayout.count():
				child = modelGridLayout.takeAt(0)
				if child.widget():
					child.widget().deleteLater()

			self.ui.templateModelsButtonGroup = qt.QButtonGroup()
			self.ui.templateModelsButtonGroup.setExclusive(False)

			colorPickers_dict={}
			opacitySliders_dict={}
			bntCnt=0
			cnt=0
			for ititle in sorted_nicely(list(modelWig_dict)):
				fontSettings = qt.QFont("font-size: 10pt;font-family: Arial")
				fontSettings.setBold(False)
				mainLabel=qt.QLabel(ititle.title())
				mainLabel.setFont(fontSettings)
				modelGridLayout.addWidget(mainLabel,cnt,0,1,2)
				titleLine = qt.QFrame()
				titleLine.setFrameShape(qt.QFrame.HLine)
				titleLine.setFixedWidth(435)
				modelGridLayout.addWidget(titleLine,cnt+1,0,1,2)
				cnt += 2
				wigCnt=1
				for iwig in modelWig_dict[ititle]:
					modelGridLayout.addWidget(iwig[1],cnt,1)
					cnt += 1
					self.ui.templateModelsButtonGroup.addButton(iwig[1].findChild(qt.QCheckBox,f'{iwig[0]}Model3DVisLeft'), bntCnt)
					self.ui.templateModelsButtonGroup.addButton(iwig[1].findChild(qt.QCheckBox,f'{iwig[0]}Model2DVisLeft'), bntCnt+1)
					self.ui.templateModelsButtonGroup.addButton(iwig[1].findChild(qt.QCheckBox,f'{iwig[0]}Model3DVisRight'), bntCnt+2)
					self.ui.templateModelsButtonGroup.addButton(iwig[1].findChild(qt.QCheckBox,f'{iwig[0]}Model2DVisRight'), bntCnt+3)
					self.ui.templateModelsButtonGroup.addButton(iwig[1].findChild(ctk.ctkColorPickerButton,f'{iwig[0]}ModelVisColor'), bntCnt+4)
					
					opacitySliders_dict[iwig[0] + 'ModelOpacity']=iwig[1].findChild(qt.QDoubleSpinBox, f'{iwig[0]}ModelOpacity')

					colorPickers_dict[iwig[0] + 'ModelVisColor']=iwig[1].findChild(ctk.ctkColorPickerButton,f'{iwig[0]}ModelVisColor')
					colorPickers_dict[iwig[0] + 'ModelVisColor'].setColor(qt.QColor(templateModelColors[iwig[0]]))

					bntCnt +=5
					if wigCnt < len(modelWig_dict[ititle]):
						sepLine = qt.QFrame()
						sepLine.setFrameShape(qt.QFrame.HLine)
						sepLine.setFixedWidth(250)
						modelGridLayout.addWidget(sepLine,cnt,1,1,1,qt.Qt.AlignRight)
						cnt += 1
						wigCnt += 1

			for slider in opacitySliders_dict:
				opacitySliders_dict[slider].valueChanged.connect(lambda _, b=opacitySliders_dict[slider]: self.onModelOpacityChange(button=b))
			
			self.templateModelVisDict={}
			children = self.ui.templateModelsVisGB.findChildren('QCheckBox')
			for i in children:
				self.templateModelVisDict[i.name]=i.isChecked()

			self.ui.templateModelsButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onTemplateGroupButton)

	def onAllModelsGroupButton(self, button):
		viewType = [x for x in ['3D','2D'] if x in button.name][0]
		viewToggle = [x for x in ['Off','On'] if x in button.name][0]

		if 'TemplateModel' in button.name:
			space=self.ui.templateSpaceCB.currentText

			self.templateModelNames=np.unique([x.split('_desc-')[-1].split('.vtk')[0] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space,  'active_models')) if x.endswith('vtk')])

			for modelName in self.templateModelNames:
				for side in {'Left', 'Right'}:
					model_name = f"tpl-{space}_*hemi-{side[0].lower()}_desc-{modelName}*"
					
					if list(slicer.util.getNodes(model_name).values()):
						model = list(slicer.util.getNodes(model_name).values())[0]
						
						if viewType == '3D':
							if viewToggle == 'On':
								model.GetDisplayNode().Visibility3DOn()
								self.uiWidget.findChild(qt.QCheckBox, modelName + 'Model' + viewType + 'Vis' + side).setChecked(True)
							elif viewToggle == 'Off':
								model.GetDisplayNode().Visibility3DOff()
								self.uiWidget.findChild(qt.QCheckBox, modelName + 'Model' + viewType + 'Vis' + side).setChecked(False)
						elif viewType == '2D':
							if viewToggle == 'On':
								model.GetDisplayNode().Visibility2DOn()
								self.uiWidget.findChild(qt.QCheckBox, modelName + 'Model' + viewType + 'Vis' + side).setChecked(True)
							elif viewToggle == 'Off':
								model.GetDisplayNode().Visibility2DOff()
								self.uiWidget.findChild(qt.QCheckBox, modelName + 'Model' + viewType + 'Vis' + side).setChecked(False)
		else:
			planName = self.ui.planName.currentText

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x) and planName in x.GetName()]
			for modelNode in models:

				descType=None
				descTypeButton=None
				modelType=None
				modelTypeButton=None

				if 'ses-pre' in modelNode.GetName():
					descType='ses-pre'
					descTypeButton='planned'
				elif 'ses-intra' in modelNode.GetName():
					descType='ses-intra'
					descTypeButton='intra'
				elif 'ses-post' in modelNode.GetName():
					descType='ses-post'
					descTypeButton='actual'

				cleanedModelName = '_'.join([x for x in modelNode.GetName().split('_') if not x.isdigit()])
				if cleanedModelName.endswith('_lead'):
					modelType='_lead'
					modelTypeButton='Lead'
				elif cleanedModelName.endswith('_contact'):
					modelType='_contact'
					modelTypeButton='Contact'
				elif cleanedModelName.endswith('_activity'):
					modelType='_activity'
					modelTypeButton='MERActivity'
				elif cleanedModelName.endswith('_track'):
					modelType='_track'
					modelTypeButton='Microelectrodes'
				elif cleanedModelName.endswith('_vta'):
					modelType='_vta'
					modelTypeButton='VTA'
				
				if None not in (descTypeButton, modelTypeButton):
					print(descTypeButton + modelTypeButton + viewType + 'Vis' + viewToggle)
					self.uiWidget.findChild(qt.QRadioButton, descTypeButton + modelTypeButton + viewType + 'Vis' + viewToggle).checked=True
					if viewToggle == 'On':
						self.uiWidget.findChild(qt.QRadioButton, descTypeButton + modelTypeButton + viewType + 'VisOff').checked=False
					else:
						self.uiWidget.findChild(qt.QRadioButton, descTypeButton + modelTypeButton + viewType + 'VisOn').checked=False

				if descType is not None and modelType is not None:
					if all([viewType == '3D', descType in modelNode.GetName(), modelType in modelNode.GetName(), 'task-' + planName in modelNode.GetName()]):
						if viewToggle == 'On':
							modelNode.GetDisplayNode().Visibility3DOn()
						else:
							modelNode.GetDisplayNode().Visibility3DOff()
					elif all([viewType == '2D', descType in modelNode.GetName(), modelType in modelNode.GetName(), 'task-' + planName in modelNode.GetName()]):
						if viewToggle == 'On':
							modelNode.GetDisplayNode().Visibility2DOn()
						else:
							modelNode.GetDisplayNode().Visibility2DOff()

	def onTemplateViewGroupButton(self, button):
		
		space = self.ui.templateSpaceCB.currentText
		self.templateModelNames = np.unique([x.split('_desc-')[(-1)].split('.vtk')[0] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models')) if x.endswith('vtk')])
		
		if button.text == 'Yes':
			with open(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models', 'template_model_colors.json')) as (settings_file):
				templateModelColors = json.load(settings_file)
			
			templateTransform = [x for x in slicer.util.getNodesByClass('vtkMRMLLinearTransformNode') if f"subject_to-{space}_xfm" in x.GetName()]
			if not templateTransform and self._parameterNode.GetParameter('derivFolder'):
				templateTransform = [x for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'space')) if f"subject_to-{space}_xfm" in os.path.basename(x) and x.endswith('.h5')]
				if templateTransform:
					templateTransform = slicer.util.loadTransform(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'space', templateTransform[0]))
			
			frameTransform = None
			if len(slicer.util.getNodes('*frame_rotation*')) > 0:
				frameTransform=list(slicer.util.getNodes('*frame_rotation*').values())[0]
				frameTransform=getReverseTransform(frameTransform)

			acpcTransformPresent = None
			acpcTransformPresent = slicer.mrmlScene.GetFirstNodeByName('acpc_transform')
			transformNodeCT = None
			if len(slicer.util.getNodes('*from-ctFrame_to*')) > 0:
				transformNodeCT = list(slicer.util.getNodes('*from-ctFrame_to*').values())[0]
			if templateTransform:
				if isinstance(templateTransform, list):
					templateTransform = templateTransform[0]

				templateTransform=getReverseTransform(templateTransform)

				if transformNodeCT is not None:
					if frameTransform is not None:
						frameTransform.SetAndObserveTransformNodeID(transformNodeCT.GetID())
						templateTransform.SetAndObserveTransformNodeID(frameTransform.GetID())
					else:
						templateTransform.SetAndObserveTransformNodeID(transformNodeCT.GetID())

			self.ui.templateModelsVisGB.collapsed = 0
			templateVolumes = glob.glob(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'templates', '*.nii*'))
			for ivol in templateVolumes:
				node = slicer.util.loadVolume(ivol)
				node.GetDisplayNode().AutoWindowLevelOff()
				
				with open(os.path.join(os.path.dirname(ivol),os.path.basename(ivol).split('.nii')[0]+'.json')) as (template_file):
					template_settings = json.load(template_file)

				node.GetDisplayNode().SetWindow(template_settings['window'])
				node.GetDisplayNode().SetLevel(template_settings['level'])
				
				if templateTransform:
					if isinstance(templateTransform, list):
						templateTransform = templateTransform[0]
					node.SetAndObserveTransformNodeID(templateTransform.GetID())

			for modelName in self.templateModelNames:
				for side in {'Right', 'Left'}:
					model_name = f"tpl-{space}_*hemi-{side[0].lower()}_desc-{modelName}.vtk"
					model_filename=glob.glob(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models', model_name))
					if model_filename:
						vtkModelBuilder = vtkModelBuilderClass()
						vtkModelBuilder.filename = model_filename[0]
						vtkModelBuilder.model_color = templateModelColors[(f"{modelName}")]
						vtkModelBuilder.model_visibility = True
						model = vtkModelBuilder.add_to_scene(True)
						model.GetDisplayNode().SetFrontfaceCulling(0)
						model.GetDisplayNode().SetBackfaceCulling(0)
						model.GetDisplayNode().VisibilityOn()
						model.GetDisplayNode().SetAmbient(0.3)
						model.GetDisplayNode().SetDiffuse(1.0)
						model.AddDefaultStorageNode()
						model.GetStorageNode().SetCoordinateSystem(coordSys)
						model.GetDisplayNode().SetSliceIntersectionThickness(2)

						if templateTransform:
							model.SetAndObserveTransformNodeID(templateTransform.GetID())
						for viewType in {'3D', '2D'}:
							self.uiWidget.findChild(qt.QCheckBox, modelName + 'Model' + viewType + 'Vis' + side).setChecked(True)

			layoutManager = slicer.app.layoutManager()
			self.dataViewVolume = layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode().GetBackgroundVolumeID()
			applicationLogic = slicer.app.applicationLogic()
			selectionNode = applicationLogic.GetSelectionNode()
			selectionNode.SetReferenceActiveVolumeID(self.dataViewVolume)
			applicationLogic.PropagateVolumeSelection(0)
			applicationLogic.FitSliceToAll()
			slicer.util.resetSliceViews()

			viewNodes = slicer.util.getNodesByClass('vtkMRMLAbstractViewNode')
			for viewNode in viewNodes:
				viewNode.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeCube)

		if button.text == 'No':

			self.ui.templateModelsVisGB.collapsed = 1
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if any(s in imodel.GetName() for s in self.templateModelNames):
					slicer.mrmlScene.RemoveNode(imodel)

			templateVolumes = glob.glob(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'templates', '*.nii*'))
			for ivol in templateVolumes:
				if len(slicer.util.getNodes(f"*{os.path.basename(ivol).split('.nii')[0]}*"))>0:
					slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes(f"*{os.path.basename(ivol).split('.nii')[0]}*").values())[0])

			if len(slicer.util.getNodes(f"*subject_to-{space}_xfm*")) > 0:
				for itrans in list(slicer.util.getNodes(f"*subject_to-{space}_xfm*").values()):
					slicer.mrmlScene.RemoveNode(itrans)

			if len(slicer.util.getNodes('*frame_rotation_reverse*')) > 0:
				slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes('*frame_rotation_reverse*').values())[0])

			layoutManager = slicer.app.layoutManager()
			self.dataViewVolume = layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode().GetBackgroundVolumeID()
			applicationLogic = slicer.app.applicationLogic()
			selectionNode = applicationLogic.GetSelectionNode()
			selectionNode.SetReferenceActiveVolumeID(self.dataViewVolume)
			applicationLogic.PropagateVolumeSelection(0)
			applicationLogic.FitSliceToAll()
			slicer.util.resetSliceViews()

	def onAllModelOpacityChange(self, button):

		if 'TemplateModels' in button.name:
			space = self.ui.templateSpaceCB.currentText
			planName = 'tpl-' + self.ui.templateSpaceCB.currentText
			templateModelNames = np.unique([x.split('_desc-')[(-1)].split('.vtk')[0] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models')) if x.endswith('vtk')])
			for modelName in templateModelNames:
				for side in {'Right', 'Left'}:
					model_name = f"tpl-{space}_hemi-{side[0].lower()}_desc-{modelName}*"
					self.uiWidget.findChild(qt.QDoubleSpinBox, modelName + 'ModelOpacity').setValue(button.value)
		else:
			planName = self.ui.planName.currentText
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x) and planName in x.GetName()]
			for modelNode in models:
				planType = [x for x in ('ses-pre', 'ses-intra', 'ses-post') if x in modelNode.GetName()]
				objectType = [x for x in ('_lead', '_contact', '_activity','_track','_vta') if x in modelNode.GetName()]

				if planType and objectType:
					objectType=objectType[0]
					planType=planType[0]

					if planType == 'ses-pre':
						descType = 'planned'
					elif planType == 'ses-intra':
						descType = 'intra'
					else:
						descType = 'actual'

					if objectType == '_lead':
						modelType = 'Lead'
					elif objectType == '_contact':
						modelType = 'Contact'
					elif objectType == '_activity':
						modelType = 'MERActivity'
					elif objectType == '_track':
						modelType = 'Microelectrodes'
					elif objectType == '_vta':
						modelType = 'VTA'
					
					#self.uiWidget.findChild(ctk.ctkSliderWidget, descType + modelType + 'Opacity').setValue(button.value)
					self.uiWidget.findChild(qt.QDoubleSpinBox, descType + modelType + 'Opacity').setValue(button.value)

	def onModelOpacityChange(self, button):
		print(button.name)
		planType = [x for x in ('planned', 'intra', 'actual', 'Model') if x in button.name][0]
		if planType == 'Model':
			space = self.ui.templateSpaceCB.currentText
			planName = 'tpl-' + self.ui.templateSpaceCB.currentText
			templateModelNames = np.unique([x.split('_desc-')[(-1)].split('.vtk')[0] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models')) if x.endswith('vtk')])
			descType = ['desc-' + x for x in templateModelNames if button.name.startswith(x)][0]
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode')]
			for imodel in models:
				if all([descType in imodel.GetName(), planName in imodel.GetName()]):
					imodel.GetDisplayNode().SetOpacity(button.value)

		else:
			planName = self.ui.planName.currentText
			if planType == 'planned':
				descType = 'ses-pre'
			elif planType == 'intra':
				descType = 'ses-intra'
			else:
				descType = 'ses-post'

			objectType = [x for x in ('Lead', 'Contact', 'MERActivity', 'Microelectrodes', 'VTA') if x in button.name][0]

			if objectType == 'Lead':
				modelType = '_lead'
			elif objectType == 'Contact':
				modelType = '_contact'
			elif objectType == 'MERActivity':
				modelType = '_activity'
			elif objectType == 'Microelectrodes':
				modelType = '_track'
			elif objectType == 'VTA':
				modelType = '_vta'

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode')]
			for imodel in models:
				if all([descType in imodel.GetName(), planName in imodel.GetName(), modelType in imodel.GetName()]):
					#self.onGroupButton(self.uiWidget.findChild(qt.QRadioButton, planType + objectType + '3DVisOn'))
					#self.onGroupButton(self.uiWidget.findChild(qt.QRadioButton, planType + objectType + '2DVisOn'))

					imodel.GetDisplayNode().SetOpacity(button.value)

	def onPlanChange(self):
		if self._parameterNode.GetParameter('derivFolder'):
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
				surgical_data = json.load(surg_file)
			planName = self.ui.planName.currentText

			if planName in list(surgical_data['trajectories']):
				self.resetValues()

	def resetValues(self):
		surgical_info = os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")
		with open(surgical_info) as (surg_file):
			surgical_info_json = json.load(surg_file)
		
		dataVisibility_info = os.path.join(self._parameterNode.GetParameter('derivFolder'), 'settings', 'model_visibility.json')
		with open(dataVisibility_info) as (vis_file):
			dataVisibility = json.load(vis_file)
		
		
		planName = self.ui.planName.currentText
		for key, val in dataVisibility.items():
			viewType = [x for x in ('3D', '2D') if x in key][0]
			planType = [x for x in ('planned', 'intra', 'actual') if x in key][0]
			objectType = [x for x in ('Lead', 'Contact', 'MERActivity', 'Microelectrodes','VTA') if x in key][0]

			object_dic = {
				'Lead':'_lead', 
				'Contact':'_contact', 
				'MERActivity':'_activity', 
				'Microelectrodes':'_track', 
				'VTA':'_vta'
			}

			if planType == 'planned':
				descType = 'ses-pre'
			elif planType == 'intra':
				descType = 'ses-intra'
			elif planType == 'actual':
				descType = 'ses-post'

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if object_dic[objectType] in x.GetName()]
			for imodel in models:
				if all([viewType == '3D', descType in imodel.GetName(), 'task-' + planName in imodel.GetName()]):
					imodel.GetDisplayNode().VisibilityOn()
					if imodel.GetDisplayNode().GetVisibility3D() == True:
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'Off').setChecked(False)
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'On').setChecked(True)
					else:
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'Off').setChecked(True)
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'On').setChecked(False)
				elif all([viewType == '2D', descType in imodel.GetName(), 'task-' + planName in imodel.GetName()]):
					imodel.GetDisplayNode().VisibilityOn()
					if imodel.GetDisplayNode().GetVisibility2D() == True:
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'Off').setChecked(False)
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'On').setChecked(True)
					else:
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'Off').setChecked(True)
						self.ui.planModelsGB.findChild(qt.QRadioButton, key + 'On').setChecked(False)

	def onGroupButton(self, button):
		"""
		When button group interaction occurs the vtk model visibility/color will
		be changed
		
		:param button: QAbstractButton object
		:type button: QAbstractButton
		"""
		if self._parameterNode.GetParameter('derivFolder'):
			viewType = [x for x in ('3D', '2D', 'Color') if x in button.name][0]
			planType = [x for x in ('planned', 'intra', 'actual') if x in button.name][0]
			objectType = [x for x in ('Lead','Contact','MERActivity','Microelectrodes','VTA') if x in button.name][0]
			object_dic = {
				'Lead':'_lead',
				'Contact':'_contact',
				'MERActivity':'_activity',
				'Microelectrodes':'_track',
				'VTA':'_vta'
			}

			if planType == 'planned':
				descType = 'ses-pre'
			elif planType == 'intra':
				descType = 'ses-intra'
			elif planType == 'actual':
				descType = 'ses-post'

			planName = self.ui.planName.currentText
			if viewType == 'Color':
				colorButton = self.uiWidget.findChild(ctk.ctkColorPickerButton, planType + objectType + 'VisColor')
				for item in [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if all(value in x.GetName() for value in (object_dic[objectType], descType, planName))]:
					item.GetDisplayNode().SetColor(hex2rgb(str(colorButton.color)))

			else:
				view = button.text
				
				if view == 'On':
					view_opposite='Off'
					turnOn = True
				else:
					view_opposite='On'
					turnOn = False

				for b in self._dictRB:
					if button.name.replace(view, '') in b:
						if not self._dictRB[b]:
							self._dictRB[b]=True
						self.ui.planModelsGB.findChild(qt.QRadioButton, b).setChecked(False)

				if self._dictRB[button.name]:
					self._dictRB[button.name] = False
					self._dictRB[button.name.replace(view, view_opposite)] = True
					self.ui.planModelsGB.findChild(qt.QRadioButton, button.name).setChecked(True)
				else:
					for b in self._dictRB:
						if button.name.replace(view, '') in b:
							self._dictRB[b] = False
					self._dictRB[button.name] = True
				
				models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if object_dic[objectType] in x.GetName()]
				for imodel in models:
					if all([viewType == '3D', descType in imodel.GetName(), 'task-' + planName in imodel.GetName()]):
						if turnOn:
							imodel.GetDisplayNode().Visibility3DOn()
						else:
							imodel.GetDisplayNode().Visibility3DOff()
					elif all([viewType == '2D', descType in imodel.GetName(), 'task-' + planName in imodel.GetName()]):
						if turnOn:
							imodel.GetDisplayNode().Visibility2DOn()
						else:
							imodel.GetDisplayNode().Visibility2DOff()

	def onTemplateGroupButton(self, button):
		"""
		When button group interaction occurs the vtk model visibility/color will
		be changed
		
		:param button: QAbstractButton object
		:type button: QAbstractButton
		"""
		print(button.name)
		space = self.ui.templateSpaceCB.currentText
		self.templateModelNames = np.unique([x.split('_desc-')[(-1)].split('.vtk')[0] for x in os.listdir(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'ext_libs', 'space', 'tpl-' + space, 'active_models')) if x.endswith('vtk')])
		viewType = [x for x in ('3D','2D','Color') if x in button.name][0]
		objectType = [x for x in self.templateModelNames if button.name.startswith(x)][0]
		
		if viewType == 'Color':
			colorButton = self.uiWidget.findChild(ctk.ctkColorPickerButton, objectType + 'ModelVisColor')
			for item in [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if 'desc-' + objectType in x.GetName().lower()]:
				item.GetDisplayNode().SetColor(hex2rgb(str(colorButton.color)))
		else:
			side = button.text
			checkbox = self.uiWidget.findChild(qt.QCheckBox, objectType + 'Model' + viewType + 'Vis' + side)

			if checkbox.isChecked():
				turnOn = True
			else:
				turnOn = False

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if 'desc-' + objectType in x.GetName()]
			for imodel in models:
				if all([viewType == '3D', f"hemi-{side[0].lower()}" in imodel.GetName()]):
					if turnOn:
						imodel.GetDisplayNode().Visibility3DOn()
					else:
						imodel.GetDisplayNode().Visibility3DOff()
				elif all([viewType == '2D', f"hemi-{side[0].lower()}" in imodel.GetName()]):
					if turnOn:
						imodel.GetDisplayNode().Visibility2DOn()
					else:
						imodel.GetDisplayNode().Visibility2DOff()
	
	def onSaveSceneButton(self):
		"""
		Slot for ``Save Slicer Scene`` button.
		
		"""
		
		sortSceneData()

		#slicer.util.saveScene(os.path.join(os.path.split(self._parameterNode.GetParameter('derivFolder'))[0], 'Scene.mrml'))


#
# dataViewLogic
#

class dataViewLogic(ScriptedLoadableModuleLogic):
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
		self.dataViewInstance = None
		self.FrameAutoDetect = False

	def getParameterNode(self, replace=False):
		"""Get the dataView parameter node.

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
		""" Create the dataView parameter node.

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
# dataViewTest
#

class dataViewTest(ScriptedLoadableModuleTest):
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
		self.test_dataView1()

	def test_dataView1(self):
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
		inputVolume = SampleData.downloadSample('dataView1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = dataViewLogic()

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
