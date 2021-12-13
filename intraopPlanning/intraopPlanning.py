import os
import sys
import shutil
import numpy as np
import csv
import json
import glob
import vtk, qt, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

if getattr(sys, 'frozen', False):
	cwd = os.path.dirname(sys.argv[0])
elif __file__:
	cwd = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.dirname(cwd))

from helpers.helpers import vtkModelBuilderClass, plotLead, rotation_matrix, warningBox, getMarkupsNode, adjustPrecision, addCustomLayouts, frame_angles, frame_angles, plotMicroelectrode
from helpers.variables import coordSys, slicerLayout, fontSetting, groupboxStyle

#
# intraopPlanning
#

class intraopPlanning(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "06: Intraop Planning"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = []
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This module loads a patient data directory for trajectoryGuide.\n
For use details see <a href="https://trajectoryguide.greydongilmore.com/widgets/01_patient_directory.html">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# intraopPlanningWidget
#

class intraopPlanningWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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

		self.leftChanIndex = {1:'anterior',  3:'posterior',  0:'medial',  2:'lateral'}
		self.rightChanIndex = {1:'anterior',  3:'posterior',  2:'medial',  0:'lateral'}
		self.intraopElecPlot = True
		self.intraopMERTracksPlot = True
		self.intraopMERActivityPlot = True
		self.intraopImplantTraj=None

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
		self.logic = intraopPlanningLogic()
		
		# Connections
		self._setupConnections()
		
	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/intraopPlanning.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)
		
		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
		fontSettings = qt.QFont(fontSetting)
		fontSettings.setBold(False)
		self.ui.intraopPlanNameGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.intraopPlanNameGB.setFont(fontSettings)
		self.ui.intraopTrajUsedGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.intraopTrajUsedGB.setFont(fontSettings)
		self.ui.intraopImplantDepthGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.intraopImplantDepthGB.setFont(fontSettings)
		self.ui.merRecordingGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.merRecordingGB.setFont(fontSettings)

	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
		
		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		
		self.ui.intraopTrajUsedButtonGroup.connect('buttonClicked(int)', self.onTrajUsedButtonGroup)
		self.ui.intraopShowLeadButtonGroup.connect('buttonClicked(int)', self.onShowLeadButtonGroup)
		self.ui.intraopShowMERTracksButtonGroup.connect('buttonClicked(int)', self.onShowMERTracksButtonGroup)
		self.ui.intraopPlanName.connect('currentIndexChanged(int)', self.onIntraopPlanChange)
		self.ui.trajNoMERButtonGroup.buttonClicked.connect(self.onTrajNoMERButton)
		self.ui.intraopMERActivityPlotButtonGroup.connect('buttonClicked(int)', self.onMERActivityPlotClicked)
		self.ui.intraopConfirmButton.connect('clicked(bool)', self.onUpdatePlannedLeads)

		self.ui.centerSlider.maximumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.centerSlider,'max'))
		self.ui.anteriorSlider.maximumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.anteriorSlider,'max'))
		self.ui.posteriorSlider.maximumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.posteriorSlider,'max'))
		self.ui.medialSlider.maximumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.medialSlider,'max'))
		self.ui.lateralSlider.maximumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.lateralSlider,'max'))
		self.ui.centerSlider.minimumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.centerSlider,'min'))
		self.ui.anteriorSlider.minimumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.anteriorSlider,'min'))
		self.ui.posteriorSlider.minimumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.posteriorSlider,'min'))
		self.ui.medialSlider.minimumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.medialSlider,'min'))
		self.ui.lateralSlider.minimumValueChanged.connect(lambda: self.onRangeSliderChange(self.ui.lateralSlider,'min'))
		
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
		self.active = False

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

			planNames = [self.ui.intraopPlanName.itemText(i) for i in range(self.ui.intraopPlanName.count)]

			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as surgical_info:
				surgical_info_json = json.load(surgical_info)

			plansAdd = [x for x in list(surgical_info_json['trajectories']) if x not in planNames]
			self.ui.intraopPlanName.addItems(plansAdd)

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

	def onRangeSliderChange(self,slider,value):
		if not slider.minimumValue == 0 and not slider.maximumValue ==0:
			if value=='max':
				checkVal=slider.maximumValue+-.5 if slider.maximumValue<0 else slider.maximumValue+.5
				if slider.minimumValue==slider.maximumValue:
					slider.minimumValue=slider.minimumValue+-.5 if slider.minimumValue<0 else slider.minimumValue+.5
			else:
				if slider.minimumValue==slider.maximumValue:
					slider.maximumValue=slider.maximumValue+-.5 if slider.maximumValue<0 else slider.maximumValue+.5

	def onTrajNoMERButton(self, button):
		"""
		Slot for trajectory used under ``Left Plan``
		
		:param button: id of button clicked
		:type button: Integer
		"""

		if 'center' in button.name:
			if self.ui.centerActivityButton.isChecked():
				self.ui.centerSlider.minimumValue = 0
				self.ui.centerSlider.maximumValue = 0
			else:
				self.ui.centerSlider.minimumValue = -1
				self.ui.centerSlider.maximumValue = 1
		elif 'anterior' in button.name:
			if self.ui.anteriorActivityButton.isChecked():
				self.ui.anteriorSlider.minimumValue = 0
				self.ui.anteriorSlider.maximumValue = 0
			else:
				self.ui.anteriorSlider.minimumValue = -1
				self.ui.anteriorSlider.maximumValue = 1
		elif 'posterior' in button.name:
			if self.ui.posteriorActivityButton.isChecked():
				self.ui.posteriorSlider.minimumValue = 0
				self.ui.posteriorSlider.maximumValue = 0
			else:
				self.ui.posteriorSlider.minimumValue = -1
				self.ui.posteriorSlider.maximumValue = 1
		elif 'medial' in button.name:
			if self.ui.medialActivityButton.isChecked():
				self.ui.medialSlider.minimumValue = 0
				self.ui.medialSlider.maximumValue = 0
			else:
				self.ui.medialSlider.minimumValue = -1
				self.ui.medialSlider.maximumValue = 1
		elif 'lateral' in button.name:
			if self.ui.lateralActivityButton.isChecked():
				self.ui.lateralSlider.minimumValue = 0
				self.ui.lateralSlider.maximumValue = 0
			else:
				self.ui.lateralSlider.minimumValue = -1
				self.ui.lateralSlider.maximumValue = 1

	def resetValues(self):
		
		self.ui.intraopElecDepth.value=0.0
		self.intraopImplantTraj=None

		children = self.ui.intraopTrajUsedGB.findChildren('QRadioButton')
		for i in children:
			i.checked = False

		children = self.ui.merRecordingGB.findChildren('QRadioButton')
		for i in children:
			i.checked = False

		children = self.ui.merRecordingGB.findChildren('ctkRangeWidget')
		for i in children:
			i.minimumValue = -1
			i.maximumValue = 1

		self.ui.PlannedElecPlotIntraopY.checked=True
		self.ui.MERTracksPlotIntraopY.checked=True
		self.ui.MERActivityPlotIntraopY.checked=True
	
	def onIntraopPlanChange(self):
		if self.active:
			if self.ui.intraopPlanName.currentText != '':
				planName = self.ui.intraopPlanName.currentText
				
				self.resetValues()

				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
					surgical_data = json.load(surg_file)
				
				if planName in list(surgical_data['trajectories']):
					if 'side' in list(surgical_data['trajectories'][planName]):
						self.updateMERLabelOrientatrion(surgical_data['trajectories'][planName]['side'])

					if 'intra' in list(surgical_data['trajectories'][planName]):
						if 'lead_traj_chosen' in list(surgical_data['trajectories'][planName]['intra']):
							if surgical_data['trajectories'][planName]['intra']['lead_traj_chosen']:
								children = self.ui.intraopTrajUsedGB.findChildren('QRadioButton')
								for i in children:
									if str(i.text).lower() == surgical_data['trajectories'][planName]['intra']['lead_traj_chosen']:
										i.checked = True
										self.postChans = str(i.text).lower()
						
						if 'lead_depth' in list(surgical_data['trajectories'][planName]['intra']):
							if surgical_data['trajectories'][planName]['intra']['lead_depth']:
								self.ui.intraopElecDepth.value = surgical_data['trajectories'][planName]['intra']['lead_depth']

						children = self.ui.merRecordingGB.findChildren('ctkRangeWidget')
						for i in children:
							
							ichan=i.name.replace('Slider','')
							
							if 'mer_tracks' in list(surgical_data['trajectories'][planName]['intra']):
								if surgical_data['trajectories'][planName]['intra']['mer_tracks']:						
									if ichan in list(surgical_data['trajectories'][planName]['intra']['mer_tracks']):
										if surgical_data['trajectories'][planName]['intra']['mer_tracks'][ichan]['mer_bot']:
											if surgical_data['trajectories'][planName]['intra']['mer_tracks'][ichan]['mer_bot']=='n/a':
												i.maximumValue=0
												self.uiWidget.findChild(qt.QRadioButton, ichan + 'ActivityButton').checked=True
											else:
												i.maximumValue=surgical_data['trajectories'][planName]['intra']['mer_tracks'][ichan]['mer_bot']
										
										if surgical_data['trajectories'][planName]['intra']['mer_tracks'][ichan]['mer_top']:
											if surgical_data['trajectories'][planName]['intra']['mer_tracks'][ichan]['mer_top']=='n/a':
												i.minimumValue=0
												self.uiWidget.findChild(qt.QRadioButton, ichan + 'ActivityButton').checked=True
											else:
												i.minimumValue=surgical_data['trajectories'][planName]['intra']['mer_tracks'][ichan]['mer_top']

						models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
						for imodel in models:
							if planName in imodel.GetName() and 'task-intra' in imodel.GetName():
								imodel.GetDisplayNode().SetVisibility(1)

	def updateMERLabelOrientatrion(self,side):
		if side == 'right':
			children = self.ui.intraopTrajUsedGB.findChildren('QRadioButton')
			for i in children:
				if i.text == 'Lateral' and i.name == 'intraLatMER':
					continue
				if i.text == 'Medial' and i.name == 'intraLatMER':
					i.text = 'Lateral'
				elif i.text == 'Lateral' and i.name == 'intraMedMER':
					i.text = 'Medial'
				elif i.text == 'Medial' and i.name == 'intraMedMER':
					continue
		else:
			children = self.ui.intraopTrajUsedGB.findChildren('QRadioButton')
			for i in children:
				if i.text == 'Lateral' and i.name == 'intraLatMER':
					i.text = 'Medial'
				elif i.text == 'Medial' and i.name == 'intraLatMER':
					continue
				elif i.text == 'Lateral' and i.name == 'intraMedMER':
					continue
				elif i.text == 'Medial' and i.name == 'intraMedMER':
					i.text = 'Lateral'

	def onMERActivityPlotClicked(self, button):
		"""
		Slot for selection of ``Plot MER Tracks`` under ``Left Plan``
		
		:param button: id of button clicked
		:type button: Integer
		"""
		if button == -2:
			self.intraopMERActivityPlot = True
		if button == -3:
			self.intraopMERActivityPlot = False

	def onTrajUsedButtonGroup(self, button):
		"""
		Slot for selection of ``Trajectory used`` under ``Left Plan``
		
		"""
		children = self.ui.intraopTrajUsedGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked():
				self.intraopImplantTraj = i.text.lower()
			i.checked = False

		button_idx = abs(button - -2)
		if children[button_idx].text.lower() != self.intraopImplantTraj:
			if self.intraopImplantTraj:
				children[button_idx].setChecked(True)
				self.intraopImplantTraj = []
			else:
				children[button_idx].setChecked(False)
				self.intraopImplantTraj = children[button_idx].text.lower()
		elif children[button_idx].text.lower() == self.intraopImplantTraj:
			children[button_idx].setChecked(True)
			self.intraopImplantTraj = []

	def onShowLeadButtonGroup(self, button):
		"""
		Slot for selection of ``Plot Planned Lead`` under ``Left Plan``
		
		:param button: id of button clicked
		:type button: Integer
		"""
		if button == -2:
			self.intraopElecPlot = True
		if button == -3:
			self.intraopElecPlot = False

	def onShowMERTracksButtonGroup(self, button):
		"""
		Slot for selection of ``Plot MER Tracks`` under ``Left Plan``
		
		:param button: id of button clicked
		:type button: Integer
		"""
		if button == -2:
			self.intraopMERTracksPlot = True
		if button == -3:
			self.intraopMERTracksPlot = False

	def onUpdatePlannedLeads(self, button):
		"""
		Slot for ``Update Plan`` buttons
		
		:param button: id of button clicked -2 for left, -3 for right
		:type button: Integer
		"""
		plan_name = self.ui.intraopPlanName.currentText

		children = self.ui.intraopTrajUsedGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked():
				self.intraopImplantTraj = i.text.lower()

		if self.intraopImplantTraj is None:
			warningBox('Please choose trajectory used.')
			return

		for item in [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if f"{plan_name}_planned_lead" in x.GetName().lower()]:
			item.GetDisplayNode().VisibilityOff()

		for item in [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if f"{plan_name}_planned_contact" in x.GetName().lower()]:
			item.GetDisplayNode().VisibilityOff()

		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (side_file):
			surgical_data = json.load(side_file)
		
		if not 'entry' in list(surgical_data['trajectories'][plan_name]['pre']):
			warningBox('Please create a preoperative plan with this plan name.')
			return

		if not 'intra' in list(surgical_data['trajectories'][plan_name]):
			surgical_data['trajectories'][plan_name]['intra']={}

		microUsed = None
		if 'microUsed' in list(surgical_data['trajectories'][plan_name]['pre']):
			microUsed = surgical_data['trajectories'][plan_name]['pre']['microUsed']

		mer_info={}
		mer_info['center']=[self.ui.centerSlider.minimumValue, self.ui.centerSlider.maximumValue]
		mer_info['anterior']=[self.ui.anteriorSlider.minimumValue, self.ui.anteriorSlider.maximumValue]
		mer_info['posterior']=[self.ui.posteriorSlider.minimumValue, self.ui.posteriorSlider.maximumValue]
		mer_info['medial']=[self.ui.medialSlider.minimumValue, self.ui.medialSlider.maximumValue]
		mer_info['lateral']=[self.ui.lateralSlider.minimumValue, self.ui.lateralSlider.maximumValue]

		entry_pre = np.array(surgical_data['trajectories'][plan_name]['pre']['entry'])
		target_pre = np.array(surgical_data['trajectories'][plan_name]['pre']['target'])
		origin_point=np.array(surgical_data['trajectories'][plan_name]['pre']['origin_point'])
		electrode_used = surgical_data['trajectories'][plan_name]['pre']['elecUsed']
		channels_used=surgical_data['trajectories'][plan_name]['pre']['chansUsed']
		implant_depth=self.ui.intraopElecDepth.value
		channel_index = self.leftChanIndex if surgical_data['trajectories'][plan_name]['side'] == 'left' else self.rightChanIndex

		#### determine coordinate roation based on pre-op coords first.
		DirVec = entry_pre - target_pre
		MagVec = np.sqrt([np.square(DirVec[0]) + np.square(DirVec[1]) + np.square(DirVec[2])])
		NormVec = np.array([float(DirVec[0] / MagVec), float(DirVec[1] / MagVec), float(DirVec[2] / MagVec)])
		
		#alpha = np.round(float(np.arccos(DirVec[0] / MagVec) * 180 / np.pi), 2)
		#alpha = np.round(float(90 - alpha), 2)
		#beta = np.round(float(np.arccos(DirVec[1] / MagVec) * 180 / np.pi), 2) - 90
		
		alpha,beta=frame_angles(target_pre,entry_pre)
		alpha = float(90 - alpha)
		beta = beta-90

		t = 2 * np.pi * np.arange(0, 1, 0.25)
		coords_shift = 2 * np.c_[(np.cos(t), np.sin(t), np.zeros_like(t))].T
		R = rotation_matrix(alpha, beta, 0)
		new_coords_shift = (np.dot(R, coords_shift).T + target_pre[:3]).T
		
		#### determine coordinates for final track chosen intraop
		if 'center' in self.intraopImplantTraj.lower():
			new_coords_shift_final = new_coords_shift
			P1_shift = new_coords_shift_final.T[2] - (new_coords_shift_final.T[2] - new_coords_shift_final.T[0]) / 2
			coords = np.hstack((P1_shift, P1_shift + NormVec.T * MagVec))
		else:
			for idx, chan in channel_index.items():
				if self.intraopImplantTraj.lower() == chan:
					coords = np.hstack((new_coords_shift.T[idx], new_coords_shift.T[idx] + NormVec.T * MagVec))

		#### apply the depth offset based on intraop electrode implant depth
		entry_intraop = list(coords[3:])
		target_intraop = list(np.array([coords[0] - NormVec[0] * implant_depth,
								coords[1] - NormVec[1] * implant_depth,
								coords[2] - NormVec[2] * implant_depth]))

		surgical_data['trajectories'][plan_name]['intra']={
			'entry':entry_intraop,
			'target':target_intraop,
			'lead_traj_chosen':self.intraopImplantTraj.lower(),
			'lead_depth':implant_depth
		}

		lineNode = getMarkupsNode(plan_name + '_line_intra', 'vtkMRMLMarkupsLineNode', False)
		if lineNode is not None:
			slicer.mrmlScene.RemoveNode(slicer.util.getNode(lineNode.GetName()))
		
		markupsNodeTrackLine = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsLineNode')
		markupsNodeTrackLine.SetName(plan_name + '_line_intra')
		markupsNodeTrackLine.GetDisplayNode().SetVisibility(0)
		markupsNodeTrackLine.AddDefaultStorageNode()
		markupsNodeTrackLine.GetStorageNode().SetCoordinateSystem(coordSys)
		
		n = markupsNodeTrackLine.AddControlPoint(vtk.vtkVector3d(entry_intraop[0], entry_intraop[1], entry_intraop[2]))
		markupsNodeTrackLine.SetNthControlPointLabel(n, 'entry')
		markupsNodeTrackLine.SetNthControlPointLocked(n, True)
		
		n = markupsNodeTrackLine.AddControlPoint(vtk.vtkVector3d(target_intraop[0], target_intraop[1], target_intraop[2]))
		markupsNodeTrackLine.SetNthControlPointLabel(n, 'target')
		markupsNodeTrackLine.SetNthControlPointLocked(n, True)
		
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'settings', 'model_visibility.json')) as (settings_file):
			slice_vis = json.load(settings_file)
		
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'settings', 'model_color.json')) as (settings_file):
			model_colors = json.load(settings_file)
		
		model_parameters = {
			'plan_name':plan_name,
			'type':'intra',
			'side': surgical_data['trajectories'][plan_name]['side'],
			'elecUsed':electrode_used,
			'microUsed': microUsed,
			'data_dir':os.path.join(self._parameterNode.GetParameter('derivFolder')),
			'lead_fileN':f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-intra_task-{plan_name}_type-{electrode_used}_label-{self.intraopImplantTraj.lower()}_lead.vtk",
			'contact_fileN':f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-intra_task-{plan_name}_type-{electrode_used}_label-%s_contact.vtk", 
			'model_col':model_colors['intraLeadColor'], 
			'model_vis':slice_vis['intraLead3DVis'], 
			'contact_col':model_colors['intraContactColor'], 
			'contact_vis':slice_vis['intraContact3DVis'],
			'plot_model':self.intraopElecPlot
		}

		models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
		for imodel in models:
			if f"ses-intra_task-{plan_name}" in imodel.GetName():
				imodel.GetDisplayNode().VisibilityOff()

		plotLead(entry_intraop.copy(),target_intraop.copy(),origin_point.copy(), model_parameters)
		
		ch_info={}
		for ichan in channels_used:
			
			activity_filename = os.path.join(self._parameterNode.GetParameter('derivFolder'), 
				f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-intra_task-{plan_name}_type-mer_label-{ichan}_activity.vtk")
			
			track_filename = os.path.join(self._parameterNode.GetParameter('derivFolder'), 
				f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-intra_task-{plan_name}_type-mer_label-{ichan}_track")
			
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if os.path.basename(activity_filename).split('.vtk')[0] in imodel.GetName():
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetID()))
				elif os.path.basename(track_filename) in imodel.GetName():
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetID()))

			coords_track=None
			coords_activity=None
			if 'center' in ichan:
				P1_shift = new_coords_shift.T[2] - (new_coords_shift.T[2] - new_coords_shift.T[0]) / 2
				coords_track = np.hstack((P1_shift, P1_shift + NormVec.T * MagVec))
				
				if not 'n/a' in mer_info[ichan] and not all(v == 0.0 for v in mer_info[ichan]):
					coords_activity = np.hstack((P1_shift + NormVec.T * (-1 * mer_info['center'][0]),P1_shift + NormVec.T * (-1 * mer_info['center'][1])))
					mer_bot = mer_info[ichan][1]
					mer_top = mer_info[ichan][0]
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
						coords_track = np.hstack((new_coords_shift.T[idx], new_coords_shift.T[idx] + NormVec.T * MagVec))
						
						if not 'n/a' in mer_info[ichan] and not all(v == 0.0 for v in mer_info[ichan]):
							coords_activity = np.hstack((new_coords_shift.T[idx] + NormVec.T * (-1 * mer_info[ichan][0]),new_coords_shift.T[idx] + NormVec.T * (-1 * mer_info[ichan][1])))
							mer_bot = mer_info[ichan][1]
							mer_top = mer_info[ichan][0]
						else:
							mer_bot = 'n/a'
							mer_top = 'n/a'

						ch_info_temp = {
							'mer_top':mer_top,
							'mer_bot':mer_bot,
							'acpc_entry':list(adjustPrecision(new_coords_shift.T[idx] + NormVec.T * MagVec)),
							'acpc_target':list(adjustPrecision(new_coords_shift.T[idx]))
						}

			if coords_track is not None and self.intraopMERTracksPlot and model_parameters['microUsed'] is not None:
				ch_info[ichan] = ch_info_temp

				model_parameters['mer_filename'] = track_filename
				model_parameters['model_col'] = model_colors['plannedMicroelectrodesColor']
				model_parameters['model_vis'] = model_colors['plannedMicroelectrodesColor']

				plotMicroelectrode(coords_track, alpha, beta, model_parameters)

			if coords_activity is not None:
				vtkModelBuilder = vtkModelBuilderClass()
				vtkModelBuilder.coords = coords_activity
				vtkModelBuilder.tube_radius = 0.3
				vtkModelBuilder.tube_tickness = 0.3
				vtkModelBuilder.filename = activity_filename
				vtkModelBuilder.model_color = model_colors['intraMERActivityColor']
				vtkModelBuilder.model_visibility = slice_vis['intraMERActivity3DVis']
				vtkModelBuilder.build_line()
				
				if self.intraopMERActivityPlot:
					vtkModelBuilder.add_to_scene()

		surgical_data['trajectories'][plan_name]['intra']['mer_tracks']=ch_info

		json_output = json.dumps(surgical_data, indent=4)
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json"), 'w') as (fid):
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

		if not os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-intra_coordsystem.json")):
			coordsystem_file_json = {}
			coordsystem_file_json['IntendedFor'] = os.path.join(self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
			coordsystem_file_json['FiducialsCoordinateSystem'] = 'RAS'
			coordsystem_file_json['FiducialsCoordinateUnits'] = 'mm'
			coordsystem_file_json['FiducialsCoordinateSystemDescription'] = "RAS orientation: Origin halfway between LPA and RPA, positive x-axis towards RPA, positive y-axis orthogonal to x-axis through Nasion,  z-axis orthogonal to xy-plane, pointing in superior direction."
			coordsystem_file_json['FiducialsCoordinates'] = {}
		else:
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-intra_coordsystem.json")) as coordsystem_file:
				coordsystem_file_json = json.load(coordsystem_file)
		
		coordsystem_file_json['IntendedFor'] = os.path.join(self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
		coordsystem_file_json['FiducialsCoordinates']['entry']=adjustPrecision(entry_intraop).tolist()
		coordsystem_file_json['FiducialsCoordinates']['target']=adjustPrecision(target_intraop).tolist()
		coordsystem_file_json['FiducialsCoordinates']['origin_point']=adjustPrecision(origin_point).tolist()

		for ichan in list(surgical_data['trajectories'][plan_name]['intra']['mer_tracks']):
			coordsystem_file_json['FiducialsCoordinates'][f"{plan_name}_{ichan}_entry"]=adjustPrecision(surgical_data['trajectories'][plan_name]['intra']['mer_tracks'][ichan]['acpc_entry']).tolist()
			coordsystem_file_json['FiducialsCoordinates'][f"{plan_name}_{ichan}_target"]=adjustPrecision(surgical_data['trajectories'][plan_name]['intra']['mer_tracks'][ichan]['acpc_target']).tolist()

		json_output = json.dumps(coordsystem_file_json, indent=4)
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-intra_coordsystem.json"), 'w') as fid:
			fid.write(json_output)
			fid.write('\n')



#
# intraopPlanningLogic
#

class intraopPlanningLogic(ScriptedLoadableModuleLogic):
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
		self.intraopPlanningInstance = None
		self.FrameAutoDetect = False

	def getParameterNode(self, replace=False):
		"""Get the intraopPlanning parameter node.

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
		""" Create the intraopPlanning parameter node.

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
# intraopPlanningTest
#

class intraopPlanningTest(ScriptedLoadableModuleTest):
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
		self.test_intraopPlanning1()

	def test_intraopPlanning1(self):
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
		inputVolume = SampleData.downloadSample('intraopPlanning1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = intraopPlanningLogic()

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
