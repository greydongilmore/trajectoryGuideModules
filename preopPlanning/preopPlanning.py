
import qt, slicer, numpy as np, vtk, os, json, sys, collections
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

if getattr(sys, 'frozen', False):
	cwd = os.path.dirname(sys.argv[0])
elif __file__:
	cwd = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.dirname(cwd))


from helpers.helpers import norm_vec, mag_vec, plotLead, warningBox, \
rotation_matrix, vtkModelBuilderClass,getMarkupsNode,getPointCoords,adjustPrecision,getFrameCenter,applyTransformToPoints,frame_angles,\
getFrameRotation,dotdict,addCustomLayouts, plotMicroelectrode

from helpers.variables import coordSys, groupboxStyle, slicerLayout, electrodeModels, microelectrodeModels

#
# preopPlanning
#

class preopPlanning(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "05: Preop Planning"  # TODO: make this more human readable by adding spaces
		self.parent.categories = ["trajectoryGuide"]  # TODO: set categories (folders where the module shows up in the module selector)
		self.parent.dependencies = []  # TODO: add here list of module names that this module requires
		self.parent.contributors = ["Greydon Gilmore (Western University)"]  # TODO: replace with "Firstname Lastname (Organization)"
		# TODO: update with short description of the module and a link to online module documentation
		self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#preopPlanning">module documentation</a>.
"""
		# TODO: replace with organization, grant and thanks
		self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""


#
# preopPlanningWidget
#

class preopPlanningWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
		self.plannedMERTracksPlot = True
		self.plannedElecPlot = True
		self.planElecModel = []
		self.lastOriginCoords = np.array([0.0,0.0,0.0])
		self.crossHairLastPosition = collections.deque(maxlen=2)
		self.originPointPrevious = None
		self.frameRotationNode = None
		self.probeEyeTransformNode = None
		self.probeEyeMarkups = None
		self.planAllChecked = False
		self.originPoint = 'mcp'
		self.merOrientation = 'plusBenGun'
		self.planRenameEvent = False
		self.previousProbeEye = False
		self.lastPlanName = None
		self.leftChanIndexPlus = {1:'anterior',  3:'posterior',  0:'medial',  2:'lateral'}
		self.rightChanIndexPlus = {1:'anterior',  3:'posterior',  2:'medial',  0:'lateral'}
		self.leftChanIndexCross = {1:'anterolateral',  3:'posteromedial',  0:'anteromedial',  2:'posterolateral'}
		self.rightChanIndexCross = {0:'anterolateral',  2:'posteromedial',  1:'anteromedial',  3:'posterolateral'}
		self.plusBenGunLabels = ['planAntMER','planPosMER','planMedMER','planLatMER','planCenMER']
		self.crossBenGunLabels = ['planAntMedMER','planAntLatMER','planPosMedMER','planPosLatMER','planCenMER']

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
		self.logic = preopPlanningLogic()

		self.setupMarkupNodes()

		# Connections
		self._setupConnections()

	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/preopPlanning.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)

		self.ui.probeEyeModelCBox.addAttribute('vtkMRMLModelNode', 'ProbeEye', '1')
		self.ui.probeEyeModelCBox.addAttribute('vtkMRMLMarkupsLineNode', 'ProbeEye', '1')
		self.ui.probeEyeModelCBox.setMRMLScene(slicer.mrmlScene)

		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
		self.ui.planNameGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.coordsGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.frameCoordsGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.planEntryGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.planTargetGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.planMERGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.planElectrodeGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.probesEyeGroup.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')

		not_resize = self.ui.planAntMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planAntMERWig.setSizePolicy(not_resize)
		self.ui.planAntMERWig.setVisible(1)
		not_resize = self.ui.planPosMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planPosMERWig.setSizePolicy(not_resize)
		self.ui.planPosMERWig.setVisible(1)
		not_resize = self.ui.planMedMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planMedMERWig.setSizePolicy(not_resize)
		self.ui.planMedMERWig.setVisible(1)
		not_resize = self.ui.planLatMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planLatMERWig.setSizePolicy(not_resize)
		self.ui.planLatMERWig.setVisible(1)
		not_resize = self.ui.planAntMedMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planAntMedMERWig.setSizePolicy(not_resize)
		self.ui.planAntMedMERWig.setVisible(0)
		not_resize = self.ui.planAntLatMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planAntLatMERWig.setSizePolicy(not_resize)
		self.ui.planAntLatMERWig.setVisible(0)
		not_resize = self.ui.planPosMedMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planPosMedMERWig.setSizePolicy(not_resize)
		self.ui.planPosMedMERWig.setVisible(0)
		not_resize = self.ui.planPosLatMERWig.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planPosLatMERWig.setSizePolicy(not_resize)
		self.ui.planPosLatMERWig.setVisible(0)

		self.ui.planElecCB.addItems(['Select Electrode']+list(electrodeModels))
		self.ui.planMicroModel.addItems(['Select Microlectrode']+list(microelectrodeModels['probes']))
		self.ui.planMicroModel.setCurrentIndex(self.ui.planMicroModel.findText(microelectrodeModels['default']))


	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

		self.crosshairNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLCrosshairNode')
		self.crosshairNode.AddObserver(slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent, self.onCursorPositionModifiedEvent)

		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		
		self.ui.crosshairUpdateButton.clicked.connect(lambda : self.onUpdateCrosshairPlanning(True))
		self.ui.crosshairUpdateFrameButton.clicked.connect(lambda : self.onUpdateCrosshairFrame(True))
		self.ui.planAdd.connect('clicked(bool)', self.onPlanAdd)
		self.ui.planDelete.connect('clicked(bool)', self.onPlanDelete)
		self.ui.planRename.connect('clicked(bool)', self.onPlanRename)
		self.ui.planAddConfirm.connect('clicked(bool)', self.onPlanAddConfirm)
		self.ui.planNameEdit.connect('returnPressed()', self.ui.planAddConfirm.click)
		self.ui.planAddCancel.connect('clicked(bool)', self.onPlanAddCancel)
		self.ui.planName.connect('currentIndexChanged(int)', self.onPlanChange)
		self.ui.planAddConfirm.setVisible(0)
		self.ui.planAddCancel.setVisible(0)
		not_resize = self.ui.planAddConfirm.sizePolicy
		not_resize.setRetainSizeWhenHidden(True)
		self.ui.planAddConfirm.setSizePolicy(not_resize)
		self.ui.planNameEdit.setVisible(0)
		self.ui.planEntryLockButton.clicked.connect(lambda : self.onButtonClick(self.ui.planEntryLockButton))
		self.ui.planEntrySetButton.clicked.connect(lambda : self.onButtonClick(self.ui.planEntrySetButton))
		self.ui.planEntryJumpButton.clicked.connect(lambda : self.onButtonClick(self.ui.planEntryJumpButton))
		self.ui.planTargetLockButton.clicked.connect(lambda : self.onButtonClick(self.ui.planTargetLockButton))
		self.ui.planTargetSetButton.clicked.connect(lambda : self.onButtonClick(self.ui.planTargetSetButton))
		self.ui.planTargetJumpButton.clicked.connect(lambda : self.onButtonClick(self.ui.planTargetJumpButton))
		self.ui.planAllMER.clicked.connect(lambda : self.onSelectAllMERClicked(self.ui.planAllMER))
		self.ui.planShowLeadButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onPlanShowLeadButtonGroup)
		self.ui.merOrientationButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onMEROrientationButtonGroup)
		self.ui.planShowMERTracksButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onPlanShowMERTracksButton)
		self.ui.originPointButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onOriginPointButtonGroup)
		self.ui.planConfirmButton.connect('clicked(bool)', self.onPlanConfirmButton)
		self.ui.probeEyeModelCBox.connect('currentNodeChanged(bool)', self.onProbeEyeCBox)
		self.ui.closeProbeEyeButton.connect('clicked(bool)', self.onProbeEyeClose)
		self.redSliceNode = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeRed')
		self.ui.MRMLSliderWidget.connect('valueChanged(double)', self.onSpinBoxValueChanged)
		
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

		if self._parameterNode is None or self._updatingGUIFromParameterNode:
			return

		#wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

		#self._parameterNode.EndModify(wasModified)

	def setupMarkupNodes(self):
		self.ui.planEntryPlaceButton.setMRMLScene(slicer.mrmlScene)
		self.ui.planEntryPlaceButton.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.planEntryPlaceButton.placeButton().show()
		self.ui.planEntryPlaceButton.deleteButton().show()
		self.ui.planTargetPlaceButton.setMRMLScene(slicer.mrmlScene)
		self.ui.planTargetPlaceButton.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.planTargetPlaceButton.placeButton().show()
		self.ui.planTargetPlaceButton.deleteButton().show()


	def onPointAdd(self, caller, event):
		activeLabel = caller.GetName()
		if 'entry' in activeLabel:
			fiducialPoint='entry'
			oppositePoint = 'target'
		else:
			fiducialPoint='target'
			oppositePoint = 'entry'

		pointCoordsWorld = None
		fiducialNode = getMarkupsNode(activeLabel)
		for ifid in range(fiducialNode.GetNumberOfControlPoints()):
			if activeLabel in fiducialNode.GetNthControlPointLabel(ifid):
				pointCoordsWorld = np.zeros(3)
				fiducialNode.GetNthControlPointPositionWorld(ifid, pointCoordsWorld)
				fiducialNode.SetNthControlPointLocked(ifid, True)
		
		if pointCoordsWorld is not None:
			origin_point_coords = getPointCoords('acpc', self.originPoint)
			
			self.frameRotationNode = getFrameRotation()

			RAStoACPC = np.array([
				[ 1, 0, 0,-origin_point_coords[0]],
				[ 0, 1, 0,-origin_point_coords[1]],
				[ 0, 0, 1,-origin_point_coords[2]],
				[ 0, 0, 0,   1]
			])

			pointCoordsACPC=np.dot(RAStoACPC, np.append(pointCoordsWorld,1))[:3]
			pointCoordsACPC=applyTransformToPoints(self.frameRotationNode, pointCoordsACPC, reverse=False)

			if 'entry' in activeLabel:
				if self.ui.planEntryX.value != pointCoordsACPC[0]: self.ui.planEntryX.value =pointCoordsACPC[0]
				if self.ui.planEntryY.value != pointCoordsACPC[1]: self.ui.planEntryY.value =pointCoordsACPC[1]
				if self.ui.planEntryZ.value != pointCoordsACPC[2]: self.ui.planEntryZ.value = pointCoordsACPC[2]
			elif 'target' in activeLabel:
				if self.ui.planEntryX.value != pointCoordsACPC[0]: self.ui.planTargetX.value =pointCoordsACPC[0]
				if self.ui.planEntryY.value != pointCoordsACPC[1]: self.ui.planTargetY.value =pointCoordsACPC[1]
				if self.ui.planEntryZ.value != pointCoordsACPC[2]: self.ui.planTargetZ.value =pointCoordsACPC[2]

			oppositePointCoords = getPointCoords((self.ui.planName.currentText + '_line'), oppositePoint, node_type='vtkMRMLMarkupsLineNode')
			if np.array_equal(adjustPrecision(oppositePointCoords), adjustPrecision(np.array([0.0] * 3))):
				oppositePointCoords = getPointCoords(oppositePoint, oppositePoint)

			if not np.array_equal(adjustPrecision(oppositePointCoords), adjustPrecision(np.array([0.0] * 3))):
				self.convertFiducialNodesToLine(fiducialPoint, oppositePoint, self.ui.planName.currentText + '_line')

	def onPointDelete(self, caller, event):
		activeLabel = caller.GetName()
		fiducialNode = getMarkupsNode(activeLabel)
		for ifid in range(fiducialNode.GetNumberOfControlPoints()):
			if activeLabel in fiducialNode.GetNthControlPointLabel(ifid):
				fiducialNode.RemoveNthControlPoint(ifid)

		planPointOrigin = getPointCoords((self.ui.planName.currentText + '_line'), activeLabel, node_type='vtkMRMLMarkupsLineNode')
		if np.array_equal(adjustPrecision(planPointOrigin), adjustPrecision(np.array([0.0] * 3))):
			if fiducialNode is not None:
				if 'entry' in activeLabel:
					self.ui.planEntryX.value = 0
					self.ui.planEntryY.value = 0
					self.ui.planEntryZ.value = 0
				elif 'target' in activeLabel:
					self.ui.planTargetX.value = 0
					self.ui.planTargetY.value = 0
					self.ui.planTargetZ.value = 0

	def onButtonClick(self, button):
		if 'Entry' in button.name:
			fiducialPoint = 'entry'
			oppositePoint = 'target'
		else:
			fiducialPoint = 'target'
			oppositePoint = 'entry'

		if 'LockButton' in button.name:
			pointLocked = True
			lineNode = getMarkupsNode((self.ui.planName.currentText + '_line'), node_type='vtkMRMLMarkupsLineNode')
			fiducialNode = getMarkupsNode(fiducialPoint)
			planPointOrigin = getPointCoords((self.ui.planName.currentText + '_line'), fiducialPoint, node_type='vtkMRMLMarkupsLineNode')
			if not np.array_equal(adjustPrecision(planPointOrigin), adjustPrecision(np.array([0.0] * 3))):
				for ifid in range(lineNode.GetNumberOfControlPoints()):
					if fiducialPoint in lineNode.GetNthControlPointLabel(ifid) and lineNode.GetNthControlPointLocked(ifid) == 1:
						pointLocked = False
						lineNode.SetNthControlPointLocked(ifid, False)

			else:
				for ifid in range(fiducialNode.GetNumberOfControlPoints()):
					if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid) and fiducialNode.GetNthControlPointLocked(ifid) == 1:
						fiducialNode.SetNthControlPointLocked(ifid, False)
						pointLocked = False

			if pointLocked:
				origin_point = getPointCoords('acpc', self.originPoint)
				button.setStyleSheet('')
				if lineNode is not None:
					for ifid in range(lineNode.GetNumberOfControlPoints()):
						if fiducialPoint in lineNode.GetNthControlPointLabel(ifid):
							pointCoordsWorld = np.zeros(3)
							lineNode.GetNthControlPointPositionWorld(ifid, pointCoordsWorld)
							lineNode.SetNthControlPointLocked(ifid, True)
							planPointOrigin = np.array(pointCoordsWorld) - origin_point

				else:
					for ifid in range(fiducialNode.GetNumberOfControlPoints()):
						if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
							pointCoordsWorld = np.zeros(3)
							fiducialNode.GetNthControlPointPositionWorld(ifid, pointCoordsWorld)
							fiducialNode.SetNthControlPointLocked(ifid, True)
							planPointOrigin = np.array(pointCoordsWorld[:3]) - origin_point

				if fiducialPoint == 'entry':
					self.ui.planEntryX.value = planPointOrigin[0]
					self.ui.planEntryY.value = planPointOrigin[1]
					self.ui.planEntryZ.value = planPointOrigin[2]
				else:
					self.ui.planTargetX.value = planPointOrigin[0]
					self.ui.planTargetY.value = planPointOrigin[1]
					self.ui.planTargetZ.value = planPointOrigin[2]

		elif 'JumpButton' in button.name:
			origin_point_coords = getPointCoords('acpc', self.originPoint)
			fiducialNode = getMarkupsNode((self.ui.planName.currentText + '_line'), node_type='vtkMRMLMarkupsLineNode')
			if fiducialNode is not None:
				for ifid in range(fiducialNode.GetNumberOfControlPoints()):
					if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
						slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(fiducialNode.GetID(), ifid)
						crossCoordsWorld = np.zeros(3)
						fiducialNode.GetNthControlPointPositionWorld(ifid, crossCoordsWorld)
						crossCoordsLocal = np.zeros(3)
						fiducialNode.GetNthControlPointPosition(ifid, crossCoordsLocal)
						self.crossHairLastPosition.append(np.array(crossCoordsLocal))

			else:
				fiducialNode = getMarkupsNode(fiducialPoint)
				if fiducialNode is not None:
					for ifid in range(fiducialNode.GetNumberOfControlPoints()):
						if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
							slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(fiducialNode.GetID(), ifid)
							crossCoordsWorld = np.zeros(3)
							fiducialNode.GetNthControlPointPositionWorld(ifid, crossCoordsWorld)
							crossCoordsLocal = np.zeros(3)
							fiducialNode.GetNthControlPointPosition(ifid, crossCoordsLocal)
							self.crossHairLastPosition.append(np.array(crossCoordsLocal))
				else:
					if self.ui.planName.currentText == '':
						warningBox(f'No point defined for {fiducialPoint}, please set a point!')
						return

			self.frameRotationNode = getFrameRotation()

			frameToRAS = np.array([
				[ 1, 0, 0, -origin_point_coords[0]],
				[ 0, 1, 0, -origin_point_coords[1]],
				[ 0, 0, 1, -origin_point_coords[2]],
				[ 0, 0, 0,   1]
			])

			crossCoordsACPC=np.dot(frameToRAS, np.append(crossCoordsWorld,1))[:3]
			crossCoordsACPC=applyTransformToPoints(self.frameRotationNode, crossCoordsACPC, reverse=False)

			if crossCoordsACPC[0] != self.ui.CrosshairCoordsPlanningX.value: self.ui.CrosshairCoordsPlanningX.value = crossCoordsACPC[0]
			if crossCoordsACPC[1] != self.ui.CrosshairCoordsPlanningY.value: self.ui.CrosshairCoordsPlanningY.value = crossCoordsACPC[1]
			if crossCoordsACPC[2] != self.ui.CrosshairCoordsPlanningZ.value: self.ui.CrosshairCoordsPlanningZ.value = crossCoordsACPC[2]

			self.onUpdateCrosshairPlanning(True)

		elif 'SetButton' in button.name:
			
			if self.ui.planName.currentText == '':
				warningBox('No plan name defined, please add a new plan!')
				return

			if self.ui.planName.currentText == 'Select plan':
				warningBox('No plan name selected, please select a plan!')
				return
			
			originPointWorld = getPointCoords('acpc', self.originPoint)
			crosshairSpinboxACPC = list([self.ui.CrosshairCoordsPlanningX.value, self.ui.CrosshairCoordsPlanningY.value, self.ui.CrosshairCoordsPlanningZ.value])
			fiducialMarkupsWorld = getPointCoords((self.ui.planName.currentText + '_line'), fiducialPoint, node_type='vtkMRMLMarkupsLineNode')
			
			self.frameRotationNode = getFrameRotation()

			#### true if a markups line does not exists for the current plan (one or no point is defined,need two points to make the line)
			if np.array_equal(adjustPrecision(fiducialMarkupsWorld), adjustPrecision(np.array([0.0] * 3))):
				fiducialMarkupsWorld = getPointCoords(fiducialPoint, fiducialPoint)

			if fiducialPoint == 'entry':
				fiducialSpinboxACPC = np.array([self.ui.planEntryX.value, self.ui.planEntryY.value, self.ui.planEntryZ.value])
			else:
				fiducialSpinboxACPC = np.array([self.ui.planTargetX.value, self.ui.planTargetY.value, self.ui.planTargetZ.value])

			#### true if fiducial point does not exists yet
			if np.array_equal(adjustPrecision(fiducialMarkupsWorld), adjustPrecision(np.array([0.0]*3))):
				#### true if entry/target plan spinboxes are being used to add the point
				if not np.array_equal(adjustPrecision(fiducialSpinboxACPC), adjustPrecision(np.array([0.0]*3))):
					print("one")
					fiducialPointRAS = np.array(fiducialSpinboxACPC)
				else:
					print("two")
					#### the user is using the crosshair distance from origin spinboxes to add the point
					if fiducialPoint == 'entry':
						self.ui.planEntryX.value = crosshairSpinboxACPC[0]
						self.ui.planEntryY.value = crosshairSpinboxACPC[1]
						self.ui.planEntryZ.value = crosshairSpinboxACPC[2]
					else:
						self.ui.planTargetX.value = crosshairSpinboxACPC[0]
						self.ui.planTargetY.value = crosshairSpinboxACPC[1]
						self.ui.planTargetZ.value = crosshairSpinboxACPC[2]

					fiducialPointRAS=crosshairSpinboxACPC
				
				#### need to transform the point into world space by adding the origin and applying frame rotation
				originCoordsCross=applyTransformToPoints(self.frameRotationNode, fiducialPointRAS, reverse=True)

				ACPCToRAS = np.array([
					[ 1, 0, 0,originPointWorld[0]],
					[ 0, 1, 0,originPointWorld[1]],
					[ 0, 0, 1,originPointWorld[2]],
					[ 0, 0, 0,   1]
				])

				originCoordsCross=np.dot(ACPCToRAS, np.append(originCoordsCross,1))[:3]
				
				fiducialNode = getMarkupsNode(fiducialPoint, 'vtkMRMLMarkupsFiducialNode')
				n = fiducialNode.AddControlPointWorld(vtk.vtkVector3d(originCoordsCross[0], originCoordsCross[1], originCoordsCross[2]))
				fiducialNode.SetNthControlPointLabel(n, fiducialPoint)
				fiducialNode.SetNthControlPointLocked(n, True)

			else:
				fiducialSpinboxWorld=applyTransformToPoints(self.frameRotationNode, fiducialSpinboxACPC.copy(), reverse=True)+originPointWorld.copy()

				#### true if the entry/target plan spinboxes are equal to the point coordinates in the markups
				#### need to check if crosshair spinboxes are different
				if np.array_equal(adjustPrecision(fiducialSpinboxWorld), adjustPrecision(np.array(fiducialMarkupsWorld))):
					print("three")
					#### true if the crosshair distance from origin spinboxes are not zero, meaning user is updating using them
					if not np.array_equal(adjustPrecision(np.array(crosshairSpinboxACPC)), adjustPrecision(np.array([0.0] * 3))):
						#### true if the crosshair distance from origin spinboxes are not equal to the entry/target plan spinboxes
						if not np.array_equal(adjustPrecision(np.array(crosshairSpinboxACPC)), adjustPrecision(fiducialSpinboxACPC)):
							print("four")
							#### the user pressed "Set Entry" after changing the crosshair spinbox values
							if fiducialPoint == 'entry':
								self.ui.planEntryX.value = crosshairSpinboxACPC[0]
								self.ui.planEntryY.value = crosshairSpinboxACPC[1]
								self.ui.planEntryZ.value = crosshairSpinboxACPC[2]
							elif fiducialPoint == 'target':
								self.ui.planTargetX.value = crosshairSpinboxACPC[0]
								self.ui.planTargetY.value = crosshairSpinboxACPC[1]
								self.ui.planTargetZ.value = crosshairSpinboxACPC[2]

							#### need to transform the coordinates to world space by adding the origin and applying frame rotation
							crosshairSpinboxWorld=applyTransformToPoints(self.frameRotationNode, crosshairSpinboxACPC, reverse=True)+originPointWorld.copy()

							lineNode = getMarkupsNode((self.ui.planName.currentText + '_line'), node_type='vtkMRMLMarkupsLineNode')
							if lineNode is not None:
								nodePresent = False
								for ifid in range(lineNode.GetNumberOfControlPoints()):
									if fiducialPoint in lineNode.GetNthControlPointLabel(ifid):
										lineNode.SetNthControlPointPositionWorld(ifid, crosshairSpinboxWorld[0], crosshairSpinboxWorld[1], crosshairSpinboxWorld[2])
										lineNode.SetNthControlPointLocked(ifid, True)
										nodePresent = True

								if not nodePresent:
									n = lineNode.AddControlPointWorld(vtk.vtkVector3d(crosshairSpinboxWorld[0], crosshairSpinboxWorld[1], crosshairSpinboxWorld[2]))
									lineNode.SetNthControlPointLabel(n, nodelabel)
									lineNode.SetNthControlPointLocked(n, True)
							else:
								fiducialNode = getMarkupsNode(fiducialPoint, 'vtkMRMLMarkupsFiducialNode')
								nodePresent = False
								for ifid in range(fiducialNode.GetNumberOfControlPoints()):
									if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
										fiducialNode.SetNthControlPointPositionWorld(ifid, crosshairSpinboxWorld[0], crosshairSpinboxWorld[1], crosshairSpinboxWorld[2])
										nodePresent = True

								if not nodePresent:
									n = fiducialNode.AddControlPointWorld(vtk.vtkVector3d(crosshairSpinboxWorld[0], crosshairSpinboxWorld[1], crosshairSpinboxWorld[2]))
									fiducialNode.SetNthControlPointLabel(n, nodelabel)
									fiducialNode.SetNthControlPointLocked(n, True)				
				else:
					#### need to bring the markups coordinates into distance from origin to compare with spinbox values
					fiducialMarkupsACPC=fiducialMarkupsWorld.copy()-originPointWorld.copy()
					fiducialMarkupsACPC=applyTransformToPoints(self.frameRotationNode, fiducialMarkupsACPC, reverse=False)

					# if the user updates the plan entry/target spin boxes then these values will differ from 
					# the coordinates of the current fiducial for this point.
					if not np.array_equal(adjustPrecision(fiducialMarkupsACPC), adjustPrecision(fiducialSpinboxACPC)):
						print("five")
						fiducialSpinboxWorld=applyTransformToPoints(self.frameRotationNode, fiducialSpinboxACPC, reverse=True)+originPointWorld.copy()

						fiducialNode = getMarkupsNode(fiducialPoint, 'vtkMRMLMarkupsFiducialNode')
						fiducialNode.RemoveAllControlPoints()

						n = fiducialNode.AddControlPointWorld(vtk.vtkVector3d(fiducialSpinboxWorld[0], fiducialSpinboxWorld[1], fiducialSpinboxWorld[2]))
						fiducialNode.SetNthControlPointLabel(n, fiducialPoint)
						fiducialNode.SetNthControlPointLocked(n, True)
					elif not np.array_equal(adjustPrecision(fiducialMarkupsACPC), adjustPrecision(crosshairSpinboxACPC)):
						print("six")
						crosshairSpinboxWorld=applyTransformToPoints(self.frameRotationNode, crosshairSpinboxACPC, reverse=True)+originPointWorld.copy()

						fiducialNode = getMarkupsNode(fiducialPoint, 'vtkMRMLMarkupsFiducialNode')
						fiducialNode.RemoveAllControlPoints()

						n = fiducialNode.AddControlPointWorld(vtk.vtkVector3d(crosshairSpinboxWorld[0], crosshairSpinboxWorld[1], crosshairSpinboxWorld[2]))
						fiducialNode.SetNthControlPointLabel(n, fiducialPoint)
						fiducialNode.SetNthControlPointLocked(n, True)
					else:
						print("seven")
						if fiducialPoint == 'entry':
							self.ui.planEntryX.value = fiducialMarkupsACPC[0]
							self.ui.planEntryY.value = fiducialMarkupsACPC[1]
							self.ui.planEntryZ.value = fiducialMarkupsACPC[2]
						else:
							self.ui.planTargetX.value = fiducialMarkupsACPC[0]
							self.ui.planTargetY.value = fiducialMarkupsACPC[1]
							self.ui.planTargetZ.value = fiducialMarkupsACPC[2]

			#if fiducialPoint == 'entry':
			#	if self.ui.planEntryX.value != self.ui.CrosshairCoordsPlanningX.value: self.ui.CrosshairCoordsPlanningX.value = self.ui.planEntryX.value
			#	if self.ui.planEntryY.value != self.ui.CrosshairCoordsPlanningY.value: self.ui.CrosshairCoordsPlanningY.value = self.ui.planEntryY.value
			#	if self.ui.planEntryZ.value != self.ui.CrosshairCoordsPlanningZ.value: self.ui.CrosshairCoordsPlanningZ.value = self.ui.planEntryZ.value
			#else:
			#	if self.ui.planTargetX.value != self.ui.CrosshairCoordsPlanningX.value: self.ui.CrosshairCoordsPlanningX.value = self.ui.planTargetX.value
			#	if self.ui.planTargetY.value != self.ui.CrosshairCoordsPlanningY.value: self.ui.CrosshairCoordsPlanningY.value = self.ui.planTargetY.value
			#	if self.ui.planTargetZ.value != self.ui.CrosshairCoordsPlanningZ.value: self.ui.CrosshairCoordsPlanningZ.value = self.ui.planTargetZ.value
#
			#self.onUpdateCrosshairPlanning(True)

			#oppositePointCoords = getPointCoords((self.ui.planName.currentText + '_line'), oppositePoint, node_type='vtkMRMLMarkupsLineNode')
			#if np.array_equal(adjustPrecision(oppositePointCoords), adjustPrecision(np.array([0.0] * 3))):
			#	oppositePointCoords = getPointCoords(oppositePoint, oppositePoint)
#
#			#if not np.array_equal(adjustPrecision(oppositePointCoords), adjustPrecision(np.array([0.0] * 3))):
			#	self.convertFiducialNodesToLine(fiducialPoint, oppositePoint, self.ui.planName.currentText + '_line')

	def onOriginPointButtonGroup(self, button):
		"""
		Slot for ``Show Planned Lead`` button group.
		
		:param button: QObject of the button clicked
		:type button: QObject
		"""
		if button.text == 'MCP':
			self.originPoint = 'mcp'
		elif button.text == 'AC':
			self.originPoint = 'ac'
		elif button.text == 'PC':
			self.originPoint = 'pc'

		if self.originPointPrevious is None:
			self.originPointPrevious = getPointCoords('acpc', 'mcp', world=True)

		originPointCoords = getPointCoords('acpc', (self.originPoint), world=True)
		oldValue=np.array([self.ui.CrosshairCoordsPlanningX.value,self.ui.CrosshairCoordsPlanningY.value,self.ui.CrosshairCoordsPlanningZ.value])
		newValue=(self.originPointPrevious + oldValue)-originPointCoords
		self.originPointPrevious=originPointCoords.copy()

		self.ui.CrosshairCoordsPlanningX.value = newValue[0]
		self.ui.CrosshairCoordsPlanningY.value = newValue[1]
		self.ui.CrosshairCoordsPlanningZ.value = newValue[2]

		if self._parameterNode.GetParameter('frame_system'):
			fc = getFrameCenter(self._parameterNode.GetParameter('frame_system'))
			if len(slicer.util.getNodes('*from-*Frame_to*')) > 0:
				originPointCoords = getPointCoords('acpc', (self.originPoint), world=True)
				
				self.frameRotationNode = getFrameRotation()

				currentframecalcPM=applyTransformToPoints(self.frameRotationNode, newValue.copy(), reverse=True)

				if 'leksell' in self._parameterNode.GetParameter('frame_system'):
					currentframecalcPM=((currentframecalcPM-fc)*np.array([-1,1,-1]))+100

				self.ui.frameCoordsPlanningX.value = currentframecalcPM[0]
				self.ui.frameCoordsPlanningY.value = currentframecalcPM[1]
				self.ui.frameCoordsPlanningZ.value = currentframecalcPM[2]

	def resetValues(self):
		self.ui.planEntryX.value = 0.0
		self.ui.planEntryY.value = 0.0
		self.ui.planEntryZ.value = 0.0
		self.ui.planTargetX.value = 0.0
		self.ui.planTargetY.value = 0.0
		self.ui.planTargetZ.value = 0.0
		self.ui.planRingAngle.value=0.0
		self.ui.planArcAngle.value=0.0

		self.planAllChecked=False

		children = self.ui.planMERGB.findChildren('QRadioButton')
		for i in children:
			if i.name in set(self.crossBenGunLabels+self.plusBenGunLabels+['planAllMER']):
				i.checked = False

		self.ui.planElecCB.setCurrentIndex(self.ui.planElecCB.findText('Select Electrode'))

		if self.ui.planName.currentText != '' and self.ui.planName.currentText != 'Select plan':

			if len(slicer.util.getNodes('entry')) == 0:
				self.markupsNodeEntry = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
				self.markupsNodeEntry.SetName('entry')
				self.markupsNodeEntry.AddDefaultStorageNode()
				self.markupsNodeEntry.GetStorageNode().SetCoordinateSystem(coordSys)
				self.ui.planEntryPlaceButton.setCurrentNode(self.markupsNodeEntry)

				self.markupsNodeEntry.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
				self.markupsNodeEntry.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)

			if len(slicer.util.getNodes('target')) == 0:
				self.markupsNodeTarget = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
				self.markupsNodeTarget.SetName('target')
				self.markupsNodeTarget.AddDefaultStorageNode()
				self.markupsNodeTarget.GetStorageNode().SetCoordinateSystem(coordSys)
				self.ui.planTargetPlaceButton.setCurrentNode(self.markupsNodeTarget)

				self.markupsNodeTarget.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
				self.markupsNodeTarget.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)

	def onPlanAdd(self):
		if not self.ui.planNameEdit.isVisible():
			self.ui.planNameEdit.setVisible(1)
			self.ui.planAddConfirm.setVisible(1)
			self.ui.planAddCancel.setVisible(1)

	def onPlanRename(self):
		if not self.ui.planNameEdit.isVisible():
			self.ui.planNameEdit.setVisible(1)
			self.ui.planAddConfirm.setVisible(1)
			self.ui.planAddCancel.setVisible(1)

		self.planRenameEvent=True

	def onPlanAddCancel(self):
		self.ui.planNameEdit.setVisible(0)
		self.ui.planNameEdit.clear()
		self.ui.planAddConfirm.setVisible(0)
		self.ui.planAddCancel.setVisible(0)

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

			lineNode = getMarkupsNode(planName + '_line', 'vtkMRMLMarkupsLineNode')
			if lineNode is not None:
				slicer.mrmlScene.RemoveNode(lineNode)
			fidNode = getMarkupsNode(planName + '_fiducials', 'vtkMRMLMarkupsFiducialNode')
			if fidNode is not None:
				slicer.mrmlScene.RemoveNode(fidNode)

	def onPlanEdit(self,newPlan):
		if self.ui.planName.currentText != '' or self.ui.planName.currentText != 'Select plan' and self._parameterNode.GetParameter('derivFolder') and self.lastPlanName is not None:
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
				surgical_data = json.load(surg_file)

			if self.lastPlanName in list(surgical_data['trajectories']):
				surgical_data['trajectories'][self.lastPlanName]['plan_name']=newPlan
				surgical_data['trajectories'][newPlan] = surgical_data['trajectories'].pop(self.lastPlanName)

				json_output = json.dumps(surgical_data, indent=4)
				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json"), 'w') as (fid):
					fid.write(json_output)
					fid.write('\n')

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if self.lastPlanName in imodel.GetName():
					oldName=imodel.GetName()
					newName=oldName.replace(self.lastPlanName,newPlan)
					imodel.SetName(newName)
					os.rename(imodel.GetStorageNode().GetFileName(),os.path.join(os.path.dirname(imodel.GetStorageNode().GetFileName()),newName+'.vtk'))

			fiducialNode = getMarkupsNode((self.ui.planName.currentText + '_line'), node_type='vtkMRMLMarkupsLineNode')
			if fiducialNode is not None:
				fiducialNode.SetName(newPlan+'_line')

			if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_coordsystem.json")):
				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_coordsystem.json")) as coordsystem_file:
					coordsystem_file_json = json.load(coordsystem_file)
				
				for key in list(coordsystem_file_json['FiducialsCoordinates']):
					if self.lastPlanName in key:
						coordsystem_file_json['FiducialsCoordinates'][key.replace(self.lastPlanName,newPlan)]=coordsystem_file_json['FiducialsCoordinates'].pop(key)

				json_output = json.dumps(coordsystem_file_json, indent=4)
				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_coordsystem.json"), 'w') as fid:
					fid.write(json_output)
					fid.write('\n')

	def onPlanAddConfirm(self):
		if self.ui.planNameEdit.text == '':
			warningBox('Pleae enter a plan name!')
			return
		
		elif self.ui.planNameEdit.text == 'Select plan':
			warningBox('Pleae select a plan!')
			return

		elif self.ui.planNameEdit.text in [self.ui.planName.itemText(i) for i in range(self.ui.planName.count)]:
			warningBox(f"A plan with the name {self.ui.planNameEdit.text} already exists!")
			return

		else:
			if self.ui.planNameEdit.isVisible():
				self.ui.planNameEdit.setVisible(0)
				self.ui.planAddConfirm.setVisible(0)
				self.ui.planAddCancel.setVisible(0)

			if self.planRenameEvent:
				self.onPlanEdit(self.ui.planNameEdit.text)
				self.ui.planName.removeItem(self.ui.planName.findText(self.lastPlanName))
				self.ui.planName.addItems([self.ui.planNameEdit.text])
				self.ui.planName.setCurrentIndex(self.ui.planName.findText(self.ui.planNameEdit.text))
				self.lastPlanName=self.ui.planNameEdit.text
				self.ui.planNameEdit.clear()
				self.planRenameEvent=False
			else:
				self.ui.planName.addItems([self.ui.planNameEdit.text])
				self.ui.planName.setCurrentIndex(self.ui.planName.findText(self.ui.planNameEdit.text))
				self.ui.planNameEdit.clear()

	def onPlanChange(self):
		if not self.planRenameEvent:
			if self.ui.planName.currentText != '' or self.ui.planName.currentText != 'Select plan' and self._parameterNode.GetParameter('derivFolder'):

				planName = self.ui.planName.currentText
				self.lastPlanName=planName

				self.resetValues()

				with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surg_file):
					surgical_data = json.load(surg_file)

				fiducialMarkupsWorld = getMarkupsNode((self.ui.planName.currentText + '_line'), node_type='vtkMRMLMarkupsLineNode')
				if fiducialMarkupsWorld is not None:
					origin_point = getPointCoords('acpc', self.originPoint)
					target_coords_world = getPointCoords(self.ui.planName.currentText + '_line', 'target',node_type='vtkMRMLMarkupsLineNode')
					entry_coords_world = getPointCoords(self.ui.planName.currentText + '_line', 'entry',node_type='vtkMRMLMarkupsLineNode')

					self.ui.planEntryX.value = entry_coords_world[0] - origin_point[0]
					self.ui.planEntryY.value = entry_coords_world[1] - origin_point[1]
					self.ui.planEntryZ.value = entry_coords_world[2] - origin_point[2]

					self.ui.planTargetX.value = target_coords_world[0] - origin_point[0]
					self.ui.planTargetY.value = target_coords_world[1] - origin_point[1]
					self.ui.planTargetZ.value = target_coords_world[2] - origin_point[2]

					arcAngle, ringAngle = frame_angles(target_coords_world.copy(),entry_coords_world.copy())
					self.ui.planRingAngle.value=ringAngle
					self.ui.planArcAngle.value=arcAngle

				if planName in list(surgical_data['trajectories']):

					origin_point = getPointCoords('acpc', self.originPoint)

					planPointsPresent=False
					if 'pre' in list(surgical_data['trajectories'][planName]):
						if 'entry' in list(surgical_data['trajectories'][planName]['pre']):
							if surgical_data['trajectories'][planName]['pre']['entry']:
								if self.ui.planEntryX.value != surgical_data['trajectories'][planName]['pre']['entry'][0] - origin_point[0]:
									self.ui.planEntryX.value = surgical_data['trajectories'][planName]['pre']['entry'][0] - origin_point[0]
								if self.ui.planEntryY.value != surgical_data['trajectories'][planName]['pre']['entry'][1] - origin_point[1]:
									self.ui.planEntryY.value = surgical_data['trajectories'][planName]['pre']['entry'][1] - origin_point[1]
								if self.ui.planEntryZ.value != surgical_data['trajectories'][planName]['pre']['entry'][2] - origin_point[2]:
									self.ui.planEntryZ.value = surgical_data['trajectories'][planName]['pre']['entry'][2] - origin_point[2]
								planPointsPresent=True
						
						if 'target' in list(surgical_data['trajectories'][planName]['pre']):
							if surgical_data['trajectories'][planName]['pre']['target']:
								if self.ui.planTargetX.value != surgical_data['trajectories'][planName]['pre']['target'][0] - origin_point[0]:
									self.ui.planTargetX.value = surgical_data['trajectories'][planName]['pre']['target'][0] - origin_point[0]
								if self.ui.planTargetY.value != surgical_data['trajectories'][planName]['pre']['target'][1] - origin_point[1]:
									self.ui.planTargetY.value = surgical_data['trajectories'][planName]['pre']['target'][1] - origin_point[1]
								if self.ui.planTargetZ.value != surgical_data['trajectories'][planName]['pre']['target'][2] - origin_point[2]:
									self.ui.planTargetZ.value = surgical_data['trajectories'][planName]['pre']['target'][2] - origin_point[2]
								planPointsPresent=True

					if planPointsPresent:
						
						if 'mer_tracks' in list(surgical_data['trajectories'][planName]['pre']):
							if surgical_data['trajectories'][planName]['pre']['mer_tracks']:
								self.planChans = []
								children = self.ui.planMERGB.findChildren('QRadioButton')
								for i in children:
									if i.name in set(self.crossBenGunLabels+self.plusBenGunLabels):
										if self.uiWidget.findChild(qt.QLabel, i.name + 'Label') is not None:
											if self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text.lower() in list(surgical_data['trajectories'][planName]['pre']['mer_tracks']):
												i.checked = True
												self.planChans.append(self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text.lower())
								
								self.merOrientation=None
								if any(x in self.planChans for x in self.leftChanIndexCross.values()):
									button_send = dotdict({'name':'crossBenGun','text':True})
								else:
									button_send = dotdict({'name':'plusBenGun','text':True})
								self.onMEROrientationButtonGroup(button_send)

								if len(self.planChans)==5:
									self.planAllChecked=True

						if 'side' in list(surgical_data['trajectories'][planName]):
							self.updateMERLabelOrientatrion(surgical_data['trajectories'][planName]['side'])

						if 'elecUsed' in list(surgical_data['trajectories'][planName]['pre']):
							if surgical_data['trajectories'][planName]['pre']['elecUsed']:
								self.ui.planElecCB.setCurrentIndex(self.ui.planElecCB.findText(surgical_data['trajectories'][planName]['pre']['elecUsed']))
								self.planElecModel = electrodeModels[self.ui.planElecCB.currentText]['filename']

						if 'microUsed' in list(surgical_data['trajectories'][planName]['pre']):
							if surgical_data['trajectories'][planName]['pre']['microUsed']:
								self.ui.planMicroModel.setCurrentIndex(self.ui.planMicroModel.findText(surgical_data['trajectories'][planName]['pre']['microUsed']))

						lineNode = getMarkupsNode((self.ui.planName.currentText + '_line'), node_type='vtkMRMLMarkupsLineNode')
						if lineNode is None:
							fiducialPointWorld = surgical_data['trajectories'][planName]['pre']['entry'].copy()
							
							n = self.markupsNodeEntry.AddControlPointWorld(vtk.vtkVector3d(fiducialPointWorld[0], fiducialPointWorld[1], fiducialPointWorld[2]))
							self.markupsNodeEntry.SetNthControlPointLabel(n, 'entry')
							self.markupsNodeEntry.SetNthControlPointLocked(n, True)

							fiducialPointWorld = surgical_data['trajectories'][planName]['pre']['target'].copy()

							n = self.markupsNodeTarget.AddControlPointWorld(vtk.vtkVector3d(fiducialPointWorld[0], fiducialPointWorld[1], fiducialPointWorld[2]))
							self.markupsNodeTarget.SetNthControlPointLabel(n, 'target')
							self.markupsNodeTarget.SetNthControlPointLocked(n, True)

							self.convertFiducialNodesToLine('target', 'entry', self.ui.planName.currentText + '_line', visibility=False)

						models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
						for imodel in models:
							if planName in imodel.GetName():
								imodel.GetDisplayNode().SetVisibility(1)
								if '_lead' in imodel.GetName() and lineNode is not None:
									lineNode.GetDisplayNode().SetVisibility(0)

	def convertFiducialNodesToLine(self, node1_name, node2_name, new_name, visibility=True):
		lineNode = getMarkupsNode(new_name, node_type='vtkMRMLMarkupsLineNode', create=True)
		entry_coords_world=None
		target_coords_world=None
		side = None
		for inode in [node1_name, node2_name]:
			node_temp = slicer.util.getNode(inode)
			if node_temp.GetNumberOfControlPoints() > 0:
				for ifid in range(node_temp.GetNumberOfControlPoints()):
					nodeCoords = np.zeros(3)
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
		lineNode.SetAttribute('ProbeEye', '1')

		for ifid in range(lineNode.GetNumberOfControlPoints()):
			if 'entry' in lineNode.GetNthControlPointLabel(ifid):
				entry_coords_world = np.zeros(3)
				lineNode.GetNthControlPointPositionWorld(ifid, entry_coords_world)
			if 'target' in lineNode.GetNthControlPointLabel(ifid):
				target_coords_world = np.zeros(3)
				lineNode.GetNthControlPointPositionWorld(ifid, target_coords_world)
				origin_point = getPointCoords('acpc', self.originPoint)
				if target_coords_world[0] < origin_point[0]:
					side='left'
				else:
					side='right'

		if side is not None:
			self.updateMERLabelOrientatrion(side)

		if entry_coords_world is not None and target_coords_world is not None:
			arcAngle, ringAngle = frame_angles(target_coords_world.copy(),entry_coords_world.copy())
			#dist=mag_vec(entry_coords_world,target_coords_world)
			self.ui.planRingAngle.value=ringAngle
			self.ui.planArcAngle.value=arcAngle

		#self.ui.probeEyeModelCBox.addNode(lineNode)

		if not visibility:
			lineNode.GetDisplayNode().SetVisibility(0)

	def probeEyeReset(self,currentPlanName):
		self.probeEyeModel = self.ui.probeEyeModelCBox.currentNode()
		
		if self.probeEyeModel.GetNodeTagName() =='MarkupsLine':
			planName = self.probeEyeModel.GetName().split('_')[0]

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if planName in imodel.GetName():
					imodel.GetModelDisplayNode().SetSliceIntersectionVisibility(0)

			for iLine in slicer.util.getNodesByClass('vtkMRMLMarkupsLineNode'):
				if planName in iLine.GetName():
					iLine.GetDisplayNode().SetVisibility(1)
					iLine.GetDisplayNode().SetSliceIntersectionVisibility(1)
		else:
			planName = [x for x in self.probeEyeModel.GetName().split('_') if 'task' in x][0].replace('task-','')

			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if planName in imodel.GetName():
					imodel.GetModelDisplayNode().SetSliceIntersectionVisibility(1)

			for iLine in slicer.util.getNodesByClass('vtkMRMLMarkupsLineNode'):
				if planName in iLine.GetName():
					iLine.GetDisplayNode().SetVisibility(0)
					iLine.GetDisplayNode().SetSliceIntersectionVisibility(0)

		if self.previousProbeEye!=currentPlanName:
			if len(slicer.util.getNodes('*probe_eye_tip*'))>0:
					slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes('*probe_eye_tip*').values())[0])

			if len(slicer.util.getNodes('*probeEyeTransform*'))>0:
				slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes('*probeEyeTransform*').values())[0])

	def onProbeEyeCBox(self,mounting='lateral-right'):
		if self.ui.probeEyeModelCBox.currentNode() is not None:
			try:
				logic = slicer.modules.volumereslicedriver.logic()
			except:
				qt.QMessageBox.warning(qt.QWidget(),'','Reslice Driver Module not Found')
				return

			
			if self.ui.probeEyeModelCBox.currentNode().GetNodeTagName() =='MarkupsLine':
				currentPlanName = self.ui.probeEyeModelCBox.currentNode().GetName().split('_')[0]
			else:
				currentPlanName = [x for x in self.ui.probeEyeModelCBox.currentNode().GetName().split('_') if 'task' in x][0].replace('task-','')

			self.probeEyeReset(currentPlanName)

			if self.previousProbeEye != currentPlanName:
				self.probeEyeTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLinearTransformNode', 'probeEyeTransform')

			# Settings
			redSettings = {'color':'Red','node':slicer.util.getNode('vtkMRMLSliceNodeRed'),'mode':6, 'angle':90 ,'flip':True}
			yellowSettings = {'color':'Yellow','node':slicer.util.getNode('vtkMRMLSliceNodeYellow'),'mode':5,'angle':180, 'flip':False}
			greenSettings = {'color':'Green','node':slicer.util.getNode('vtkMRMLSliceNodeGreen'),'mode':4,'angle':180, 'flip':False}

			layoutManager=slicer.app.layoutManager()
			for settings in [redSettings, yellowSettings, greenSettings]:
				logic.SetDriverForSlice(self.probeEyeTransformNode.GetID(),settings['node'])
				logic.SetModeForSlice(settings['mode'],settings['node'])
				logic.SetRotationForSlice(settings['angle'],settings['node'])
				logic.SetFlipForSlice(settings['flip'],settings['node'])
				if self.previousProbeEye != currentPlanName:
					layoutManager.sliceWidget(settings['color']).sliceLogic().FitSliceToAll()
					fov=layoutManager.sliceWidget(settings['color']).sliceLogic().GetSliceNode().GetFieldOfView()
					layoutManager.sliceWidget(settings['color']).sliceLogic().GetSliceNode().SetFieldOfView(fov[0]/3,fov[1]/3,fov[2])

			#mouseTrack = SteeredPolyAffineRegistrationLogic(self.ui.MRMLSliderWidget)
			#mouseTrack.run()

			if self.previousProbeEye == currentPlanName:
				self.probeEyeProcess(self.ui.MRMLSliderWidget.value)
			else:
				self.previousProbeEye=currentPlanName
				self.probeEyeProcess(0)

	def probeEyeProcess(self, newValue,mounting='lateral-right'):
		
		self.probeEyeModel = self.ui.probeEyeModelCBox.currentNode()
		
		if self.probeEyeModel.GetNodeTagName() =='MarkupsLine':
			planName = self.probeEyeModel.GetName().split('_')[0]
		else:
			planName = [x for x in self.probeEyeModel.GetName().split('_') if 'task' in x][0].replace('task-','')
		
		self.ProbeEntryPoint = getPointCoords((planName + '_line'), 'entry', node_type='vtkMRMLMarkupsLineNode')
		self.ProbeTargetPoint = getPointCoords((planName + '_line'), 'target', node_type='vtkMRMLMarkupsLineNode')
		
		arcAngle, ringAngle = frame_angles(self.ProbeTargetPoint,self.ProbeEntryPoint)

		# Get ring and arc directions
		if mounting == 'lateral-right':
			initDirection = [0, 1, 0]
			ringDirection = [1, 0, 0]
			arcDirection =  [0, -np.sin(np.deg2rad(ringAngle)), np.cos(np.deg2rad(ringAngle))]
		elif mounting == 'lateral-left':
			initDirection = [0, -1, 0]
			ringDirection = [-1, 0, 0]
			arcDirection  = [0, np.sin(np.deg2rad(ringAngle)), np.cos(np.deg2rad(ringAngle))]
		elif mounting == 'sagittal-anterior':
			initDirection = [-1, 0, 0]
			ringDirection = [0, 1, 0]
			arcDirection  = [np.sin(np.deg2rad(ringAngle)), 0, np.cos(np.deg2rad(ringAngle))]
		elif mounting == 'sagittal-posterior':
			initDirection = [1, 0, 0]
			ringDirection = [0, -1, 0]
			arcDirection  = [-np.sin(np.deg2rad(ringAngle)), 0, np.cos(np.deg2rad(ringAngle))]

		if newValue==0:
			layoutManager = slicer.app.layoutManager()
			self.ProbeEyeVolume = slicer.util.getNode(layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode().GetBackgroundVolumeID())
			self.ProbeEyeVolumeSpacing = self.ProbeEyeVolume.GetSpacing()
			self.ProbeMagVec=mag_vec(self.ProbeEntryPoint, self.ProbeTargetPoint)
			self.ProbeNormVec=norm_vec(self.ProbeEntryPoint, self.ProbeTargetPoint)
			self.ui.trajectoryLen.value = self.ProbeMagVec
			self.ui.MRMLSliderWidget.minimum = -1 * (self.ProbeMagVec + 30)
			self.ui.MRMLSliderWidget.maximum = 20
			self.ui.MRMLSliderWidget.value = -1 * (self.ProbeMagVec-self.ProbeEyeVolumeSpacing[2])
			startVal = -1 *(self.ProbeMagVec-self.ProbeEyeVolumeSpacing[2])
			self.ProbeEyeModelNewPoint = self.ProbeTargetPoint + startVal * self.ProbeNormVec

			#self.redSliceNode=slicer.util.getNode('vtkMRMLSliceNodeRed')
			#self.redSliceNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.onRedSliceChange)

			probeEyeMarkups = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode', 'probe_eye_tip')
			nodeDisplayNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsDisplayNode')
			probeEyeMarkups.SetAndObserveDisplayNodeID(nodeDisplayNode.GetID())
			nodeDisplayNode.SetGlyphType(3)
			nodeDisplayNode.SetTextScale(0)
			nodeDisplayNode.SetGlyphScale(4)
			nodeDisplayNode.SetUseGlyphScale(0)
			nodeDisplayNode.SetSelectedColor(1,0,0)
			probeEyeMarkups.AddControlPointWorld(vtk.vtkVector3d(0,0,0))
			probeEyeMarkups.SetAndObserveTransformNodeID(self.probeEyeTransformNode.GetID())

		else:
			self.ProbeEyeModelNewPoint = self.ProbeTargetPoint + (newValue * self.ProbeNormVec)

		# Create vtk Transform
		vtkTransform = vtk.vtkTransform()
		vtkTransform.Translate(self.ProbeEyeModelNewPoint)
		vtkTransform.RotateWXYZ(arcAngle, arcDirection[0], arcDirection[1], arcDirection[2])
		vtkTransform.RotateWXYZ(ringAngle, ringDirection[0], ringDirection[1], ringDirection[2])
		vtkTransform.RotateWXYZ(90, initDirection[0], initDirection[1], initDirection[2])

		self.probeEyeTransformNode.SetAndObserveTransformToParent(vtkTransform)
	
	def onSpinBoxValueChanged(self, newValue):
		if self.ui.probeEyeModelCBox.currentNode() is not None:
			self.probeEyeProcess(newValue)

	def onProbeEyeClose(self):
		"""
		Slot for ``Close Probe's Eye`` button.
		"""
		if self.ui.probeEyeModelCBox.currentNode() is not None:
			currentProbeEyeModel = self.ui.probeEyeModelCBox.currentNode()

			self.ui.probeEyeModelCBox.setCurrentNode(None)

			self.previousProbeEye=False

			if currentProbeEyeModel.GetNodeTagName() =='MarkupsLine':
				planName = currentProbeEyeModel.GetName().split('_')[0]

				models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
				for imodel in models:
					if planName in imodel.GetName():
						imodel.GetModelDisplayNode().SetSliceIntersectionVisibility(1)

				for iLine in slicer.util.getNodesByClass('vtkMRMLMarkupsLineNode'):
					if planName in iLine.GetName():
						iLine.GetDisplayNode().SetVisibility(0)
						iLine.GetDisplayNode().SetSliceIntersectionVisibility(0)

			else:
				planName = [x for x in currentProbeEyeModel.GetName().split('_') if 'task' in x][0].replace('task-','')

				models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
				for imodel in models:
					if planName in imodel.GetName():
						imodel.GetModelDisplayNode().SetSliceIntersectionVisibility(1)

				for iLine in slicer.util.getNodesByClass('vtkMRMLMarkupsLineNode'):
					if planName in iLine.GetName():
						iLine.GetDisplayNode().SetSliceIntersectionVisibility(1)

			if len(slicer.util.getNodes('*probe_eye_tip*'))>0:
					slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes('*probe_eye_tip*').values())[0])

			if len(slicer.util.getNodes('*probeEyeTransform*'))>0:
				slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes('*probeEyeTransform*').values())[0])

			orientations = {
				'Red':'Axial', 
				'Yellow':'Sagittal', 
				'Green':'Coronal'
			}

			layoutManager = slicer.app.layoutManager()
			for sliceViewName in layoutManager.sliceViewNames():
				layoutManager.sliceWidget(sliceViewName).mrmlSliceNode().SetOrientation(orientations[sliceViewName])

			slicer.util.resetSliceViews()

	def onCursorPositionModifiedEvent(self, caller=None, event=None):
		crosshairNode = caller
		if all([crosshairNode.GetCrosshairMode() == 1, self.active]):
			cursorRAS = np.zeros(3)
			self.crosshairNode.GetCursorPositionRAS(cursorRAS)
			crossHairRAS = np.array(self.crosshairNode.GetCrosshairRAS())
			self.crossHairLastPosition.append(cursorRAS.copy())
			if np.array_equal(adjustPrecision(crossHairRAS), adjustPrecision(self.crossHairLastPosition[0])):

				crossHairRAS = np.array(self.crosshairNode.GetCrosshairRAS())

				self.frameRotationNode = getFrameRotation()

				origin_point_coords=getPointCoords('acpc', self.originPoint, world=True)

				frameToRAS = np.array([
					[ 1, 0, 0, -origin_point_coords[0]],
					[ 0, 1, 0, -origin_point_coords[1]],
					[ 0, 0, 1, -origin_point_coords[2]],
					[ 0, 0, 0,   1]
				])

				crossHairACPC=np.dot(frameToRAS, np.append(crossHairRAS,1))[:3]
				crossHairACPC=applyTransformToPoints(self.frameRotationNode, crossHairACPC, reverse=False)

				self.lastOriginCoords = crossHairACPC.copy()
				
				self.ui.CrosshairCoordsPlanningX.value = crossHairACPC[0]
				self.ui.CrosshairCoordsPlanningY.value = crossHairACPC[1]
				self.ui.CrosshairCoordsPlanningZ.value = crossHairACPC[2]
				
				if self._parameterNode.GetParameter('frame_system'):
					fc = getFrameCenter(self._parameterNode.GetParameter('frame_system'))
					if 'leksell' in self._parameterNode.GetParameter('frame_system'):
						RASToFrame = np.array([
							[ -1, 0, 0, -fc[0]],
							[ 0, 1, 0, -fc[1]],
							[ 0, 0, -1, -fc[2]],
							[ 0, 0, 0,   1]
						])
						coordsFrame=np.dot(RASToFrame, np.append(crossHairRAS,1))[:3]
						frameToRAS = np.array([
							[ 1, 0, 0, 100],
							[ 0, 1, 0, 100],
							[ 0, 0, 1, 100],
							[ 0, 0, 0,   1]
						])
						frameCoordinates=np.dot(frameToRAS, np.append(coordsFrame,1))[:3]
					else:
						frameCoordinates=originCoordsACPC-fc

					self.ui.frameCoordsPlanningX.value = frameCoordinates[0]
					self.ui.frameCoordsPlanningY.value = frameCoordinates[1]
					self.ui.frameCoordsPlanningZ.value = frameCoordinates[2]

	def onUpdateCrosshairPlanning(self, button):
		"""
		Slot for ``Update Crosshairs`` button
		"""

		coordsACPC = np.array([self.ui.CrosshairCoordsPlanningX.value, self.ui.CrosshairCoordsPlanningY.value, self.ui.CrosshairCoordsPlanningZ.value])

		self.frameRotationNode = getFrameRotation()

		originRAS=getPointCoords('acpc', self.originPoint, world=True)
		coordsRAS=applyTransformToPoints(self.frameRotationNode, coordsACPC, reverse=True)

		ACPCToRAS = np.array([
			[ 1, 0, 0,originRAS[0]],
			[ 0, 1, 0,originRAS[1]],
			[ 0, 0, 1,originRAS[2]],
			[ 0, 0, 0,   1]
		])

		coordsRAS=np.dot(ACPCToRAS, np.append(coordsRAS,1))[:3]
		
		self.crosshairNode.SetCrosshairRAS(vtk.vtkVector3d(coordsRAS[0], coordsRAS[1], coordsRAS[2]))
		sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
		for islice in sliceNodes:
			islice.JumpSlice(coordsRAS[0], coordsRAS[1], coordsRAS[2])
		
		if self._parameterNode.GetParameter('frame_system'):
			fc = getFrameCenter(self._parameterNode.GetParameter('frame_system'))
			
			if 'leksell' in self._parameterNode.GetParameter('frame_system'):
				RASToFrame = np.array([
					[ -1, 0, 0, -fc[0]],
					[ 0, 1, 0, -fc[1]],
					[ 0, 0, -1, -fc[2]],
					[ 0, 0, 0,   1]
				])
				coordsFrame=np.dot(RASToFrame, np.append(coordsRAS,1))[:3]
				frameToRAS = np.array([
					[ 1, 0, 0, 100],
					[ 0, 1, 0, 100],
					[ 0, 0, 1, 100],
					[ 0, 0, 0,   1]
				])
				coordsFrame=np.dot(frameToRAS, np.append(coordsFrame,1))[:3]
			else:
				coordsFrame=coordsRAS-fc

			self.ui.frameCoordsPlanningX.value = coordsFrame[0]
			self.ui.frameCoordsPlanningY.value = coordsFrame[1]
			self.ui.frameCoordsPlanningZ.value = coordsFrame[2]

	def onUpdateCrosshairFrame(self, button):
		"""
		Slot for ``Update Crosshairs`` button
		"""
		if self._parameterNode.GetParameter('frame_system'):
			coordsFrame = np.array([self.ui.frameCoordsPlanningX.value, self.ui.frameCoordsPlanningY.value, self.ui.frameCoordsPlanningZ.value])

			self.frameRotationNode = getFrameRotation()
			originRAS=getPointCoords('acpc', self.originPoint, world=True)

			fc = getFrameCenter(self._parameterNode.GetParameter('frame_system'))

			if 'leksell' in self._parameterNode.GetParameter('frame_system'):
				frameToRAS = np.array([
					[ -1, 0, 0, 100],
					[ 0, 1, 0, -100],
					[ 0, 0, -1, 100],
					[ 0, 0, 0,   1]
				])
				coordsFrame=np.dot(frameToRAS, np.append(coordsFrame,1))[:3]

				RASToFrame = np.array([
					[ 1, 0, 0, fc[0]],
					[ 0, 1, 0, fc[1]],
					[ 0, 0, 1, fc[2]],
					[ 0, 0, 0,   1]
				])
				coordsRAS=np.dot(RASToFrame, np.append(coordsFrame,1))[:3]
			else:
				frameToRAS = np.array([
					[ 1, 0, 0, fc[0]],
					[ 0, 1, 0, fc[1]],
					[ 0, 0, 1, fc[2]],
					[ 0, 0, 0,   1]
				])
				coordsRAS=np.dot(frameToRAS, np.append(coordsFrame,1))[:3]

			self.crosshairNode.SetCrosshairRAS(vtk.vtkVector3d(coordsRAS[0], coordsRAS[1], coordsRAS[2]))
			sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
			for islice in sliceNodes:
				islice.JumpSlice(coordsRAS[0], coordsRAS[1], coordsRAS[2])
			
			originRAS=getPointCoords('acpc', self.originPoint, world=True)

			frameToACPC = np.array([
				[ 1, 0, 0, -originRAS[0]],
				[ 0, 1, 0, -originRAS[1]],
				[ 0, 0, 1, -originRAS[2]],
				[ 0, 0, 0,   1]
			])

			coordsACPC=np.dot(frameToACPC, np.append(coordsRAS,1))[:3]
			coordsACPC=applyTransformToPoints(self.frameRotationNode, coordsACPC, reverse=False)

			self.ui.CrosshairCoordsPlanningX.value = coordsACPC[0]
			self.ui.CrosshairCoordsPlanningY.value = coordsACPC[1]
			self.ui.CrosshairCoordsPlanningZ.value = coordsACPC[2]

	def onMEROrientationButtonGroup(self, button):
		"""
		
		"""
		if button.name != self.merOrientation:
			children = self.ui.planMERGB.findChildren('QRadioButton')
			for i in children:
				if i.name in set(self.crossBenGunLabels+self.plusBenGunLabels+['planAllMER']):
					if 'All' in i.text:
						i.checked = False
						self.planAllChecked=False
					else:
						i.checked = False
				
			if button.name == 'plusBenGun' and button.name != self.merOrientation:
				self.merOrientation = 'plusBenGun'
				self.ui.planAntMedMERWig.setVisible(0)
				self.ui.planAntLatMERWig.setVisible(0)
				self.ui.planPosMedMERWig.setVisible(0)
				self.ui.planPosLatMERWig.setVisible(0)

				self.ui.planMedMERWig.setVisible(1)
				self.ui.planLatMERWig.setVisible(1)
				self.ui.planAntMERWig.setVisible(1)
				self.ui.planPosMERWig.setVisible(1)
				self.ui.plusBenGun.setChecked(True)
			elif button.name == 'crossBenGun' and button.name != self.merOrientation:
				self.merOrientation = 'crossBenGun'
				self.ui.planAntMedMERWig.setVisible(1)
				self.ui.planAntLatMERWig.setVisible(1)
				self.ui.planPosMedMERWig.setVisible(1)
				self.ui.planPosLatMERWig.setVisible(1)
				self.ui.crossBenGun.setChecked(True)

				self.ui.planMedMERWig.setVisible(0)
				self.ui.planLatMERWig.setVisible(0)
				self.ui.planAntMERWig.setVisible(0)
				self.ui.planPosMERWig.setVisible(0)
	
	def updateMERLabelOrientatrion(self,side):
		if side == 'right':
			children = self.ui.planMERGB.findChildren('QRadioButton')
			if self.merOrientation=='plusBenGun':
				for i in children:
					if i.name in self.plusBenGunLabels:
						if self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Medial' and i.name == 'planLatMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Lateral'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Lateral' and i.name == 'planMedMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Medial'
			else:
				for i in children:
					if i.name in self.crossBenGunLabels:
						if self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Anteromedial' and i.name == 'planAntLatMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Anterolateral'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Anterolateral' and i.name == 'planAntMedMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Anteromedial'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Posteromedial' and i.name == 'planPosLatMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Posterolateral'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Posterolateral' and i.name == 'planPosMedMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Posteromedial'
		else:
			children = self.ui.planMERGB.findChildren('QRadioButton')
			if self.merOrientation=='plusBenGun':
				for i in children:
					if i.name in self.plusBenGunLabels:
						if self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Lateral' and i.name == 'planLatMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Medial'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Medial' and i.name == 'planMedMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Lateral'
			else:
				for i in children:
					if i.name in self.crossBenGunLabels:
						if self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Anterolateral' and i.name == 'planAntLatMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Anteromedial'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Anteromedial' and i.name == 'planAntMedMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Anterolateral'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Posterolateral' and i.name == 'planPosLatMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Posteromedial'
						elif self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text == 'Posteromedial' and i.name == 'planPosMedMER':
							self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text = 'Posterolateral'

	def onSelectAllMERClicked(self, button):
		"""
		Slot for ``All`` button in ``Left Plan - MER Tracks``
		
		:param button: status of button being clicked
		:type button: Boolean
		"""

		if self.merOrientation == 'plusBenGun':
			labels=self.plusBenGunLabels
		else:
			labels=self.crossBenGunLabels

		if 'planAllMER' == button.name:
			if self.uiWidget.findChild(qt.QRadioButton, 'planAllMER').isChecked() and not self.planAllChecked:
				children = self.ui.planMERGB.findChildren('QRadioButton')
				for i in children:
					if 'All' in i.text:
						continue
					elif i.name in labels:
						i.checked = True

				self.planAllChecked=True
			else:
				children = self.ui.planMERGB.findChildren('QRadioButton')
				for i in children:
					if 'All' in i.text:
						i.checked = False
					elif i.name in labels:
						i.checked = False
				self.planAllChecked=False

	

	def onPlanShowLeadButtonGroup(self, button):
		"""
		Slot for ``Show Planned Lead`` button group.
		
		:param button: QObject of the button clicked
		:type button: QObject
		"""
		if button.text == 'Yes':
			self.plannedElecPlot = True
		else:
			self.plannedElecPlot = False

	def onPlanShowMERTracksButton(self, button):
		"""
		Slot for ``Show MER Tracks`` button group.
		
		:param button: QObject of the button clicked
		:type button: QObject
		"""
		if button.text == 'Yes':
			self.plannedMERTracksPlot = True
		else:
			self.plannedMERTracksPlot = False

	def onPlanConfirmButton(self):
		"""
		Slot for Planned Preop Confirm button
		
		:param button: ID of button
		:type button: Integer
		"""

		plan_name = self.ui.planName.currentText
		origin_point = getPointCoords('acpc', self.originPoint)
		
		self.planChans = []
		children = self.ui.planMERGB.findChildren('QRadioButton')
		for i in children:
			if 'All' in i.text:
				continue
			elif i.isChecked():
				if i.name in set(self.crossBenGunLabels+self.plusBenGunLabels):
					self.planChans.append(self.uiWidget.findChild(qt.QLabel, i.name + 'Label').text.lower())

		if self.plannedMERTracksPlot and self.ui.planMicroModel.currentText == 'Select Microelectrode':
			warningBox('Please choose an microelectrode model.')
			return

		if self.ui.planElecCB.currentText == 'Select Electrode':
			warningBox('Please choose an electrode model.')
			return

		if sum(np.array([self.ui.planEntryX.value, self.ui.planEntryY.value, self.ui.planEntryZ.value])) == 0:
			warningBox('Please choose entry point.')
			return

		if sum(np.array([self.ui.planTargetX.value, self.ui.planTargetY.value, self.ui.planTargetZ.value])) == 0:
			warningBox('Please choose target point.')
			return

		self.planElecModel = electrodeModels[self.ui.planElecCB.currentText]['filename']

		self.ct_frame_present = False
		if len(slicer.util.getNodes('*from-*Frame_to*')) > 0:
			self.ct_frame_present = True

		#file = os.path.join(self._parameterNode.GetParameter('derivFolder'), 'summaries', 'patient_summary.json')
		#with open(file) as (patient_file):
		#	patient_info_json = json.load(patient_file)

		models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
		for imodel in models:
			if 'ses-pre_task-' + plan_name in imodel.GetName():
				os.remove(imodel.GetStorageNode().GetFileName())
				slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetName()))

		entry_coords_world = getPointCoords((plan_name + '_line'), 'entry', node_type='vtkMRMLMarkupsLineNode')
		target_coords_world = getPointCoords((plan_name + '_line'), 'target', node_type='vtkMRMLMarkupsLineNode')
		
		if self.merOrientation=='plusBenGun':
			channel_index = self.leftChanIndexPlus if target_coords_world[0] < origin_point[0] else self.rightChanIndexPlus
		else:
			channel_index = self.leftChanIndexCross if target_coords_world[0] < origin_point[0] else self.rightChanIndexCross
		
		trajectory_dist = np.linalg.norm(entry_coords_world.copy() - target_coords_world.copy())

		if self._parameterNode.GetParameter('frame_system'):
			
			if len(slicer.util.getNodes('*from-*Frame_to*')) > 0:
				
				frame_entry=entry_coords_world.copy()
				frame_target=target_coords_world.copy()

				if 'leksell' in self._parameterNode.GetParameter('frame_system'):
					frame_entry=(frame_entry*np.array([-1,1,-1]))+100
					frame_target=(frame_target*np.array([-1,1,-1]))+100

				self.frameRotationNode = getFrameRotation()

				arcAngle, ringAngle = frame_angles(target_coords_world.copy(),entry_coords_world.copy())

		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surgical_file):
			surgical_data = json.load(surgical_file)

		
		if self.ui.planElecCB.currentText == 'Select Electrode':
			warningBox('You need to choose an electrode model.')
			return

		
		surgical_data['trajectories'][plan_name] = {
			'side':'left' if target_coords_world[0] < origin_point[0] else 'right', 
			'pre':{
				'entry':list(adjustPrecision(entry_coords_world)), 
				'target':list(adjustPrecision(target_coords_world)), 
				'origin_point':list(adjustPrecision(origin_point)), 
				'chansUsed':self.planChans, 
				'chanIndex':channel_index,
				'elecUsed':self.ui.planElecCB.currentText, 
				'microUsed': self.ui.planMicroModel.currentText if self.ui.planMicroModel.currentText != 'Select Microelectrode' else [],
				'traj_len':float(adjustPrecision(trajectory_dist)) if self.ct_frame_present else [],
				'axial_ang':float(adjustPrecision(ringAngle)) if self.ct_frame_present else [],
				'sag_ang': float(adjustPrecision(arcAngle)) if self.ct_frame_present else [], 
				'frame_entry':list(adjustPrecision(frame_entry)) if self.ct_frame_present else [], 
				'frame_target':list(adjustPrecision(frame_target)) if self.ct_frame_present else [], 
				'mer_tracks':{}
			}
		}

		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'settings', 'model_visibility.json')) as (settings_file):
			slice_vis = json.load(settings_file)
		
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'settings', 'model_color.json')) as (settings_file):
			model_colors = json.load(settings_file)
		
		model_parameters = {
			'plan_name':plan_name,
			'type':'pre',
			'side': surgical_data['trajectories'][plan_name]['side'],
			'elecUsed':self.ui.planElecCB.currentText, 
			'microUsed': surgical_data['trajectories'][plan_name]['pre']['microUsed'],
			'data_dir':self._parameterNode.GetParameter('derivFolder'),
			'lead_fileN':f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_task-{plan_name}_type-{self.planElecModel.lower()}_lead.vtk",
			'contact_fileN':f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_task-{plan_name}_type-{self.planElecModel.lower()}_label-%s_contact.vtk", 
			'model_col':model_colors['plannedLeadColor'], 
			'model_vis':slice_vis['plannedLead3DVis'], 
			'contact_col':model_colors['plannedContactColor'], 
			'contact_vis':slice_vis['plannedContact3DVis'],
			'plot_model':self.plannedElecPlot
		}
		
		lineNode = getMarkupsNode((plan_name + '_line'), node_type='vtkMRMLMarkupsLineNode')
		lineNode.GetDisplayNode().SetVisibility(0)
		
		plotLead(entry_coords_world.copy(),target_coords_world.copy(),origin_point, model_parameters)
		
		DirVec = entry_coords_world - target_coords_world
		MagVec = np.sqrt([np.square(DirVec[0]) + np.square(DirVec[1]) + np.square(DirVec[2])])
		NormVec = np.array([float(DirVec[0] / MagVec), float(DirVec[1] / MagVec), float(DirVec[2] / MagVec)])
		
		#alpha = adjustPrecision(float(np.arccos(DirVec[0] / MagVec) * 180 / np.pi))
		#alpha = adjustPrecision(float(90 - alpha))
		#beta = adjustPrecision(float(np.arccos(DirVec[1] / MagVec) * 180 / np.pi)) - 90
		
		alpha,beta=frame_angles(target_coords_world,entry_coords_world)
		alpha = float(90 - alpha)
		beta = beta-90
		if self.merOrientation =='crossBenGun':
			R = rotation_matrix(alpha, beta, 45)
		else:
			R = rotation_matrix(alpha, beta, 0)
		t = 2 * np.pi * np.arange(0, 1, 0.25)
		coords_norm = 2 * np.c_[(np.cos(t), np.sin(t), np.zeros_like(t))].T
		new_coords_final = (np.dot(R, coords_norm).T + target_coords_world).T

		
		ch_info={}
		for ichan in self.planChans:
			mer_filename = os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_task-{plan_name}_type-mer_label-{ichan}_track")
			
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if os.path.basename(mer_filename).split('.vtk')[0] in imodel.GetName():
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetID()))

			coords=None
			if 'center' in ichan:
				P1_shift = new_coords_final.T[2] - (new_coords_final.T[2] - new_coords_final.T[0]) / 2
				coords = np.hstack((P1_shift, P1_shift + NormVec.T * MagVec))

				ch_info_temp = {
					'acpc_entry':list(adjustPrecision(P1_shift + NormVec.T * MagVec)),
					'acpc_target':list(adjustPrecision(P1_shift))
				}
			else:
				for idx, chan in channel_index.items():
					if ichan == chan:
						coords = np.hstack((new_coords_final.T[idx], new_coords_final.T[idx] + NormVec.T * MagVec))
						ch_info_temp = {
							'acpc_entry':list(adjustPrecision(new_coords_final.T[idx] + NormVec.T * MagVec)),
							'acpc_target':list(adjustPrecision(new_coords_final.T[idx]))
						}

			if coords is not None and self.plannedMERTracksPlot:
				ch_info[ichan] = ch_info_temp

				model_parameters['mer_filename'] = mer_filename
				model_parameters['model_col'] = model_colors['plannedMicroelectrodesColor']
				model_parameters['model_vis'] = model_colors['plannedMicroelectrodesColor']

				plotMicroelectrode(coords, alpha, beta, model_parameters)

		surgical_data['trajectories'][plan_name]['pre']['mer_tracks']=ch_info

		jsonfile = os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")
		json_output = json.dumps(surgical_data, indent=4)
		with open(jsonfile, 'w') as (fid):
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

		if not os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_coordsystem.json")):
			coordsystem_file_json = {}
			coordsystem_file_json['IntendedFor'] = os.path.join(self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
			coordsystem_file_json['FiducialsCoordinateSystem'] = 'RAS'
			coordsystem_file_json['FiducialsCoordinateUnits'] = 'mm'
			coordsystem_file_json['FiducialsCoordinateSystemDescription'] = "RAS orientation: Origin halfway between LPA and RPA, positive x-axis towards RPA, positive y-axis orthogonal to x-axis through Nasion,  z-axis orthogonal to xy-plane, pointing in superior direction."
			coordsystem_file_json['FiducialsCoordinates'] = {}
		else:
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_coordsystem.json")) as coordsystem_file:
				coordsystem_file_json = json.load(coordsystem_file)
		
		coordsystem_file_json['IntendedFor'] = os.path.join(self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
		coordsystem_file_json['FiducialsCoordinates'][f'{plan_name}_entry']=adjustPrecision(entry_coords_world).tolist()
		coordsystem_file_json['FiducialsCoordinates'][f'{plan_name}_target']=adjustPrecision(target_coords_world).tolist()
		coordsystem_file_json['FiducialsCoordinates']['origin_point']=adjustPrecision(origin_point).tolist()

		for ichan in list(surgical_data['trajectories'][plan_name]['pre']['mer_tracks']):
			coordsystem_file_json['FiducialsCoordinates'][f"{plan_name}_{ichan}_entry"]=adjustPrecision(surgical_data['trajectories'][plan_name]['pre']['mer_tracks'][ichan]['acpc_entry']).tolist()
			coordsystem_file_json['FiducialsCoordinates'][f"{plan_name}_{ichan}_target"]=adjustPrecision(surgical_data['trajectories'][plan_name]['pre']['mer_tracks'][ichan]['acpc_target']).tolist()

		json_output = json.dumps(coordsystem_file_json, indent=4)
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_ses-pre_coordsystem.json"), 'w') as fid:
			fid.write(json_output)
			fid.write('\n')


#
# preopPlanningLogic
#

class SteeredPolyAffineRegistrationLogic(object):
	def __init__(self, sliderWig):

		self.sliceWidgetsPerStyle = {}		
		self.interactorObserverTags = []
		self.sliderWig = sliderWig

	def run(self):
		layoutManager = slicer.app.layoutManager()
		sliceNodeCount = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLSliceNode')
		for nodeIndex in range(sliceNodeCount):
			# find the widget for each node in scene
			sliceNode = slicer.mrmlScene.GetNthNodeByClass(nodeIndex, 'vtkMRMLSliceNode')
			sliceWidget = layoutManager.sliceWidget(sliceNode.GetLayoutName())

			if sliceWidget:
				# sliceWidget to operate on and convenience variables
				# to access the internals
				style = sliceWidget.sliceView().interactorStyle()
				self.interactor = style.GetInteractor()
				
				self.sliceWidgetsPerStyle[self.interactor] = sliceWidget
				self.sliceLogic = sliceWidget.sliceLogic()
				self.sliceView = sliceWidget.sliceView()
				
				
				events = (
					vtk.vtkCommand.MouseMoveEvent,
					vtk.vtkCommand.MouseWheelForwardEvent,
					vtk.vtkCommand.MouseWheelBackwardEvent)
				for e in events:
					tag = self.interactor.AddObserver(e, self.processEvent, 1.0)
					self.interactorObserverTags.append(tag)

				

	def processEvent(self,caller=None, event=None):

		eventProcessed = None
		from slicer import app
		layoutManager = slicer.app.layoutManager()
		if caller in list (self.sliceWidgetsPerStyle):

			sliceWidget = self.sliceWidgetsPerStyle[caller]
			interactor = sliceWidget.sliceView().interactorStyle().GetInteractor()

			self.lastDrawnSliceWidget = sliceWidget
			if any(x == event for x in ("MouseWheelForwardEvent","MouseWheelBackwardEvent")):

				"""
				xy = style.GetInteractor().GetEventPosition()
				xyz = sliceWidget.sliceView().convertDeviceToXYZ(xy)
				ras = sliceWidget.sliceView().convertXYZToRAS(xyz)

				w = slicer.modules.SteeredPolyAffineRegistrationWidget

				movingRAStoIJK = vtk.vtkMatrix4x4()
				w.movingSelector.currentNode().GetRASToIJKMatrix(movingRAStoIJK)

				ijk = movingRAStoIJK.MultiplyPoint(ras + (1,))
				"""
				
				xy = interactor.GetEventPosition()
				xyz = sliceWidget.sliceView().convertDeviceToXYZ(xy)
				ras = sliceWidget.sliceView().convertXYZToRAS(xyz)
				print(ras)
				self.sliderWig.value = self.sliderWig.value-(self.sliderWig.value-ras[2])

				
				self.abortEvent(event)	  
			else:
				eventProcessed = None


	def abortEvent(self,event):
		"""Set the AbortFlag on the vtkCommand associated
		with the event - causes other things listening to the
		interactor not to receive the events"""
		# TODO: make interactorObserverTags a map to we can
		# explicitly abort just the event we handled - it will
		# be slightly more efficient
		for tag in self.interactorObserverTags:
			cmd = self.interactor.GetCommand(tag)
			cmd.SetAbortFlag(1)


class preopPlanningLogic(ScriptedLoadableModuleLogic):
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
		self.preopPlanningInstance = None
		self.FrameAutoDetect = False

	def getParameterNode(self, replace=False):
		"""Get the preopPlanning parameter node.

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
		""" Create the preopPlanning parameter node.

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
# preopPlanningTest
#

class preopPlanningTest(ScriptedLoadableModuleTest):
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
		self.test_preopPlanning1()

	def test_preopPlanning1(self):
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
		inputVolume = SampleData.downloadSample('preopPlanning1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = preopPlanningLogic()

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
