"""
Created on Mon Jan 27 17:31:54 2020

@author: greydon
"""
import numpy as np
import qt, ctk, os, sys, slicer, vtk, json
from slicer.util import VTKObservationMixin

class settingsPanelWidget(qt.QGroupBox, VTKObservationMixin):
	"""
	**Constructor - Main patientDirectoryWidget object**

	Initializes the patient directory widget.

	:param parameters: A dictionary of several important directory paths.
	:type parameters: Dictionary
	
	"""
	def __init__(self):
		qt.QGroupBox.__init__(self)
		VTKObservationMixin.__init__(self)  # needed for parameter node observation

		self._parameterNode = None

		self.setup()

	def setup(self):
		if getattr(sys, 'frozen', False):
			self.script_path = os.path.dirname(sys.argv[0])
		elif __file__:
			self.script_path = os.path.dirname(os.path.realpath(__file__))
		
		self.setLayout(qt.QFormLayout())
		self._loadUI()

		self.orientationMark = False

		# Create logic class. Logic implements all computations that should be possible to run
		# in batch mode, without a graphical user interface.
		self.logic = settingsPanelLogic()

		#### Create menu for volume combobox in settings panel
		self.volumeMenu = qt.QMenu()
		self.volumeMenuGroup = qt.QActionGroup(self.volumeMenu)
		self.volumeMenuGroup.setExclusive(True)
		self.ui.volumeButton.setMenu(self.volumeMenu)

		buttonIconSize=qt.QSize(36, 36)
		
		self._parameterNode = self.logic.getParameterNode()

		self.ui.recenterButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'recenter_light.png')))
		self.ui.recenterButton.setIconSize(buttonIconSize)
		self.ui.windowVolButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'window_level_light.png')))
		self.ui.windowVolButton.setIconSize(buttonIconSize)
		self.ui.crosshairToggleButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'crosshair_light.png')))
		self.ui.crosshairToggleButton.setIconSize(buttonIconSize)
		self.ui.linkViewsButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'unlink_light.png')))
		self.ui.linkViewsButton.setIconSize(buttonIconSize)
		self.ui.volumeButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'volumes_light.png')))
		self.ui.volumeButton.setIconSize(buttonIconSize)
		self.ui.orientationMarkerButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'orientation_light.png')))
		self.ui.orientationMarkerButton.setIconSize(buttonIconSize)

		self._setupConnections()

	def _loadUI(self):
		path = os.path.join(self.script_path, 'Resources', 'UI', 'settingsPanel.ui')
		uiWidget = slicer.util.loadUI(path)
		self.layout().addWidget(uiWidget)
		
		self.ui = slicer.util.childWidgetVariables(uiWidget)

	def _setupConnections(self):

		appLogic = slicer.app.applicationLogic()
		interactionNode = appLogic.GetInteractionNode()
		self.interactionNodeTag = interactionNode.AddObserver(interactionNode.InteractionModeChangedEvent, self.onWindowLevelInteration)

		self.ui.crosshairToggleButton.connect('clicked(bool)', self.onCrosshairToggleButton)
		self.ui.windowVolButton.connect('clicked(bool)', self.onWindowVolButton)
		self.ui.linkViewsButton.connect('clicked(bool)', self.onLinkViewsButton)
		self.ui.recenterButton.connect('clicked(bool)', self.onRecenterButton)
		self.ui.volumeButton.triggered.connect(self.onVolumeButtonChange)
		self.ui.orientationMarkerButton.clicked.connect(self.onToggleOrientationMarker)

		slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeAddedEvent, self.onScalerVolumeNodeAdded)
		slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeAboutToBeRemovedEvent, self.onScalerVolumeNodeRemoved)

		# Make sure parameter node is initialized (needed for module reload)
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

		self._parameterNode = inputParameterNode

	def onCrosshairToggleButton(self):
		"""
		Slot for ``Turn On Crosshairs`` button.
		"""
		self.crossHairNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLCrosshairNode')
		if self.crossHairNode.GetCrosshairMode() == 0:
			self.crossHairNode.SetCrosshairMode(1)
			self.ui.crosshairToggleButton.setStyleSheet("background-color: green")
		else:
			self.crossHairNode.SetCrosshairMode(0)
			self.ui.crosshairToggleButton.setStyleSheet("")

	def onWindowVolButton(self):
		currentMode = slicer.app.applicationLogic().GetInteractionNode().GetCurrentInteractionMode()
		if currentMode != 5:
			slicer.app.applicationLogic().GetInteractionNode().SetCurrentInteractionMode(slicer.vtkMRMLInteractionNode.AdjustWindowLevel)
			self.ui.windowVolButton.setStyleSheet("background-color: green")
		else:
			slicer.app.applicationLogic().GetInteractionNode().SetCurrentInteractionMode(2)
			self.ui.windowVolButton.setStyleSheet("")

	def onLinkViewsButton(self):
		""" Slot for when the "Link Views" button is pressed in the settings panel.
		
		Toggles link/unlink of slice controls across views.
		
		"""
		defaultSliceCompositeNode = slicer.mrmlScene.GetDefaultNodeByClass('vtkMRMLSliceCompositeNode')
		if not defaultSliceCompositeNode:
			defaultSliceCompositeNode = slicer.mrmlScene.CreateNodeByClass('vtkMRMLSliceCompositeNode')
			slicer.mrmlScene.AddDefaultNode(defaultSliceCompositeNode)
		
		sliceCompositeNodes = slicer.util.getNodesByClass('vtkMRMLSliceCompositeNode')

		if any([x for x in sliceCompositeNodes if not x.GetLinkedControl()]):
			for sliceCompositeNode in sliceCompositeNodes:
				sliceCompositeNode.SetLinkedControl(True)

			self.ui.linkViewsButton.setStyleSheet('background-color: green')
			self.ui.linkViewsButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'link_light.png')))
			self.ui.linkViewsButton.setIconSize(qt.QSize(36, 36))
		else:
			for sliceCompositeNode in sliceCompositeNodes:
				sliceCompositeNode.SetLinkedControl(False)

			self.ui.linkViewsButton.setStyleSheet('')
			self.ui.linkViewsButton.setIcon(qt.QIcon(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'icons', 'unlink_light.png')))
			self.ui.linkViewsButton.setIconSize(qt.QSize(36, 36))
	
	def onRecenterButton(self):
		""" Slot for when the "Recenter" button is pressed in the settings panel.
		
		Recenters the current volume on all slice views.
		
		"""
		volumeName=None
		if volumeName is None:
			for iaction in self.volumeMenu.actions():
				if iaction.isChecked():
					volumeName=iaction.text

		if volumeName is not None:
			applicationLogic = slicer.app.applicationLogic()
			selectionNode = applicationLogic.GetSelectionNode()
			selectionNode.SetReferenceActiveVolumeID(slicer.util.getNode(volumeName).GetID())
			slicer.util.resetSliceViews()

	def onVolumeButtonChange(self, sender):
		volName=sender.text
		if volName != '':

			for iaction in self.volumeMenu.actions():
				if iaction.text != volName:
					iaction.setChecked(False)
				else:
					iaction.setChecked(True)

			views = ['Red', 'Yellow', 'Green']
			for view in views:
				view_logic = slicer.app.layoutManager().sliceWidget(view).sliceLogic()
				view_cn = view_logic.GetSliceCompositeNode()
				view_cn.SetBackgroundVolumeID(slicer.util.getNode(volName).GetID())

			#slicer.util.setSliceViewerLayers(background=slicer.util.getNode(volName), foreground=None)

	def onToggleOrientationMarker(self):
		if not self.orientationMark:
			self.orientationMark = True
			self.ui.orientationMarkerButton.setStyleSheet("background-color: green")
			viewNodes = slicer.util.getNodesByClass('vtkMRMLAbstractViewNode')
			for viewNode in viewNodes:
				viewNode.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeCube)
		else:
			self.orientationMark = False
			self.ui.orientationMarkerButton.setStyleSheet("")
			viewNodes = slicer.util.getNodesByClass('vtkMRMLAbstractViewNode')
			for viewNode in viewNodes:
				viewNode.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeNone)

	@vtk.calldata_type(vtk.VTK_OBJECT)
	def onScalerVolumeNodeAdded(self, caller, event, calldata):
		node = calldata
		if isinstance(node, slicer.vtkMRMLScalarVolumeNode):
			volMenu = self.volumeMenu.addAction(node.GetName())
			volMenu.setObjectName(node.GetName())
			volMenu.setCheckable(True)

			for iaction in self.volumeMenu.actions():
				if iaction.text != node.GetName():
					iaction.setChecked(False)
				else:
					iaction.setChecked(True)

			if 'coreg' not in node.GetName():
				file_sidecar = None
				if 'derivFolder' in self._parameterNode.GetParameterNames():
					if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), node.GetName() + '.json')):
						with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), node.GetName() + '.json')) as (file):
							file_sidecar = json.load(file)
					elif os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'),'frame', node.GetName() + '.json')):
						with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame', node.GetName() + '.json')) as (file):
							file_sidecar = json.load(file)
					
					if file_sidecar is not None:
						if np.all([not file_sidecar['coregistered'], file_sidecar['vol_type'] != 'reference']):
							node.SetAttribute('coreg', '0')
							node.SetAttribute('regVol', '0')
							#self.regWidget.regFloatingCB.addItem(node.GetName())
							#index = self.regWidget.regFloatingCB.findText(node.GetName(), qt.Qt.MatchFixedString)
							#item = self.regWidget.regFloatingCB.model().item(index, 0)
							#item.setCheckState(qt.Qt.Checked)

	@vtk.calldata_type(vtk.VTK_OBJECT)
	def onScalerVolumeNodeRemoved(self, caller, event, calldata):
		node = calldata
		if isinstance(node, slicer.vtkMRMLScalarVolumeNode):
			if node.GetName() != '':
				layoutManager = slicer.app.layoutManager()
				volumeNode = slicer.util.getNode(layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode().GetBackgroundVolumeID())
				for iaction in self.volumeMenu.actions():
					if node.GetName() in iaction.text:
						self.volumeMenu.removeAction(self.volumeMenu.findChild(qt.QAction,iaction.text))
					else:
						if iaction.text == volumeNode.GetName():
							iaction.setChecked(True)
						else:
							iaction.setChecked(False)

	def onWindowLevelInteration(self, caller, event):
		""" Observer for when the window/level tool is being used.
		:param observer: observer
		:param eventid: event ID

		"""
		if 'derivFolder' in self._parameterNode.GetParameterNames():
			currentWLVolume = []
			currentMode = slicer.app.applicationLogic().GetInteractionNode().GetCurrentInteractionMode()
			if currentMode == 5:
				sliceNodes = ['Red','Green','Yellow']
				for islice in sliceNodes:
					currentWLVolume.append(slicer.util.getNode(slicer.util.getNode('vtkMRMLSliceCompositeNode' + islice).GetBackgroundVolumeID()).GetName())
				currentWLVolume = np.unique(currentWLVolume)
			elif currentMode == 2:
				sliceNodes = ['Red','Green','Yellow']
				for islice in sliceNodes:
					currentWLVolume.append(slicer.util.getNode(slicer.util.getNode('vtkMRMLSliceCompositeNode' + islice).GetBackgroundVolumeID()).GetName())
				currentWLVolume = np.unique(currentWLVolume)
				
			if len(currentWLVolume) > 0:
				currentWLVolumeFinal = []
				for islice in currentWLVolume:
					currentVol = slicer.util.getNode(islice)
					currentWindow = currentVol.GetDisplayNode().GetWindow()
					currentLevel = currentVol.GetDisplayNode().GetLevel()
					files = [x for x in os.listdir(self._parameterNode.GetParameter('derivFolder')) if any(x.endswith(y) for y in {'.nii','.nii.gz'})]
					file_sidecar = []
					for f in files:	
						with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + ".json")) as fid:
							filenames = json.load(fid)

						if filenames['node_name'] == currentVol.GetName():
							file_sidecar = filenames

					if file_sidecar:
						if np.any([currentWindow != file_sidecar['window'], currentLevel != file_sidecar['level']]):
							currentWLVolumeFinal.append(islice)
							file_sidecar_final = file_sidecar
						
				if len(currentWLVolumeFinal)==1:
					if file_sidecar_final:
						currentVol = slicer.util.getNode(currentWLVolumeFinal[0])
						currentWindow = currentVol.GetDisplayNode().GetWindow()
						currentLevel = currentVol.GetDisplayNode().GetLevel()
						file_sidecar_final['window'] = currentWindow if currentWindow != file_sidecar_final['window'] else file_sidecar_final['window']
						file_sidecar_final['level'] = currentLevel if currentLevel != file_sidecar_final['level'] else file_sidecar_final['level']
						json_temp = os.path.join(self._parameterNode.GetParameter('derivFolder'), file_sidecar_final['file_name'].split('.nii')[0] + '.json')
						json_output = json.dumps(file_sidecar_final, indent=4)
						with open(json_temp, 'w') as fid:
							fid.write(json_output)
							fid.write('\n')
						print('Updated volume: {} with window {} and level {}'.format(currentVol.GetName(), file_sidecar_final['window'], file_sidecar_final['level']))
				


#
# settingsPanelLogic
#

class settingsPanelLogic():
	"""This class should implement all the actual
	computation done by your module.  The interface
	should be such that other python code can import
	this class and make use of the functionality without
	requiring an instance of the Widget.
	Uses ScriptedLoadableModuleLogic base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""
	def getParameterNode(self, replace=False):
		"""Get the frameDetect parameter node.

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
		""" Create the frameDetect parameter node.

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

