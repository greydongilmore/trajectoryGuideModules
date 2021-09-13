import os
import sys
import shutil
import numpy as np
import csv
import json
import vtk, qt, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

if getattr(sys, 'frozen', False):
	cwd = os.path.dirname(sys.argv[0])
elif __file__:
	cwd = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.dirname(cwd))

from helpers.helpers import frameDetection, customEventFilter, warningBox,writeFCSV, addCustomLayouts
from helpers.variables import coordSys, slicerLayout,groupboxStyle, groupboxStyleTitle, slicerLayoutAxial, surgical_info_dict

#
# frameDetect
#

class frameDetect(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "02: Frame Detection"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = []
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This module performs stereotactic frame detection for frame systems: Leksell, CRW, and BRW.\n
For use details see <a href="https://trajectoryguide.greydongilmore.com/widgets/04_frame_detection.html">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# frameDetectWidget
#

class frameDetectWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
		self.logic = frameDetectLogic()

		self.frame_settings = None
		self.originalFrameVolSidecar = None
		self.framePointsManual = {}
		self.frameSystem = None
		self.framePreviousWindow = None
		self.framePreviousLevel = None

		self.ui.frameFidVolumeCBox.setMRMLScene(slicer.mrmlScene)
		self.ui.frameFiducialWig.setVisible(0)

		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()

		self.ui.advancedSettingsGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + ';}' + groupboxStyleTitle + f"color: {self.text_color}" + ';}')
		self.ui.transformTypeCB.addItems(['Rigidbody (6 DOF)', 'Similarity (7 DOF)', 'Affine (9 DOF)'])
		self.ui.transformTypeCB.setCurrentIndex(self.ui.transformTypeCB.findText('Rigidbody (6 DOF)'))
		self.ui.advancedSettingsGB.collapsed = 1

		# Connections
		self._setupConnections()

	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/frameDetect.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.customEventFilter = customEventFilter()
		self.uiWidget.setMRMLScene(slicer.mrmlScene)

	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		self.ui.frameFidVolumeCBox.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
		self.ui.frameSystemBG.connect('buttonClicked(QAbstractButton*)', self.updateParameterNodeFromGUI)
		
		self.ui.frameDetectButton.clicked.connect(self.onFrameDetectButton)
		self.ui.frameFidVolumeCBox.connect("currentNodeChanged(vtkMRMLNode*)", self.onFrameVolumeCB)
		self.ui.frameFidConfirmButton.connect('clicked(bool)', self.onFrameFidConfirmButton)
		self.ui.manualDetectionButton.connect('clicked(bool)', self.onManualDetectButton)
		self.ui.showFrameLegendButton.connect('clicked(bool)', self.onShowFrameLegendButton)
		self.ui.frameFidButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onFrameFidButtonGroup)

		self.ui.p1FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p1FramePoint))
		self.ui.p2FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p2FramePoint))
		self.ui.p3FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p3FramePoint))
		self.ui.p4FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p4FramePoint))
		self.ui.p5FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p5FramePoint))
		self.ui.p6FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p6FramePoint))
		self.ui.p7FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p7FramePoint))
		self.ui.p8FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p8FramePoint))
		self.ui.p9FramePoint.activeMarkupsPlaceModeChanged.connect(lambda: self.onPointClick(self.ui.p9FramePoint))

		self.ui.frameSystemBG.connect('buttonClicked(int)', self.onFrameSystemButtonGroupClicked)

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

		wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

		if self.ui.frameFidVolumeCBox.currentNode() is not None and not self._parameterNode.GetParameter("derivFolder"):
			derivFolder = os.path.dirname(self.ui.frameFidVolumeCBox.currentNode().GetStorageNode().GetFileName())
			self._parameterNode.SetParameter("derivFolder", derivFolder)

		if isinstance(caller, qt.QRadioButton):
			print(caller.name)
			self._parameterNode.SetParameter("frame_system", caller.name)

		self._parameterNode.EndModify(wasModified)

	def resetValues(self):

		# remove any slice annotations
		view = slicer.app.layoutManager().sliceWidget("Red").sliceView()
		view.cornerAnnotation().ClearAllTexts()
		view.cornerAnnotation().GetTextProperty().SetColor(1, 1, 1)
		view.cornerAnnotation().GetTextProperty().ShadowOn()
		view.forceRender()

		sliceAnnotations = slicer.modules.DataProbeInstance.infoWidget.sliceAnnotations
		sliceAnnotations.sliceViewAnnotationsEnabled=True
		sliceAnnotations.updateSliceViewFromGUI()

		models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
		for imodel in models:
			if f"space-{self.frameSystem}_label-" in imodel.GetName():
				slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetID()))

		fcsvNodeName = f"*{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_*desc-%s_fids*"

		searchNodes=['*sourceFiducialModel*',fcsvNodeName % ('fiducials'),fcsvNodeName % ('topbottom'),
			fcsvNodeName % ('N1'),fcsvNodeName % ('N2'),fcsvNodeName % ('N3'),'*frame_center*',
			'*from-fiducials_to-localizer_xfm*', '*arcToFrame*','*arc_collar*','*centerOfMass*',
			f"*space-{self.frameSystem}_acq-glyph_label-*",f"*space-{self.frameSystem}_acq-tube_label-*"
		]
		
		for inode in searchNodes:
			if len(slicer.util.getNodes(inode))>0:
				slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes(inode).values())[0])

		if self.ui.frameFidVolumeCBox.currentNode() is not None:
			removeVolume = self.ui.frameFidVolumeCBox.currentNode()

		originalFilename=[x for x in removeVolume.GetName().split('_') if not any(y in x for y in ('desc','ses','space'))]
		
		#### if True then the frame registration has not been saved yet, load frame scan from root directory
		if len(os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame')))==0:
			searchDirectory=self._parameterNode.GetParameter('derivFolder')
		else:
			searchDirectory=os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame')

		if self.originalFrameVolSidecar is None:
			file_sidecar_temp=[]
			for ifile in [x for x in os.listdir(searchDirectory) if x.endswith('.json')]:
				with open(os.path.join(searchDirectory,ifile)) as (file):
					file_sidecar_temp = json.load(file)
				
				if 'node_name' in list(file_sidecar_temp):
					if all(x in file_sidecar_temp['node_name'] for x in originalFilename):
						self.originalFrameVolSidecar = file_sidecar_temp
						break
		
		destinationFilename=os.path.join(self._parameterNode.GetParameter('derivFolder'), '_'.join([x for x in self.originalFrameVolSidecar['file_name'].split('_') if not any(y in x for y in ('desc','ses','space'))]))
		
		if not os.path.exists(destinationFilename):
			shutil.copy2(os.path.join(self._parameterNode.GetParameter('derivFolder'),'source',self.originalFrameVolSidecar['source_name']),destinationFilename)

		self.originalFrameVolSidecar['file_name']=os.path.basename(destinationFilename)
		self.originalFrameVolSidecar['node_name']=os.path.basename(destinationFilename).split('.nii')[0]
		self.originalFrameVolSidecar['vol_type']=''

		json_output = json.dumps(self.originalFrameVolSidecar, indent=4)
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), self.originalFrameVolSidecar['node_name']+'.json'), 'w') as (fid):
			fid.write(json_output)
			fid.write('\n')
		
		frameFidVolume=slicer.util.loadVolume(destinationFilename)
		frameFidVolume.SetName(self.originalFrameVolSidecar['node_name'])

		slicer.mrmlScene.RemoveNode(removeVolume)

		if len(slicer.util.getNodes(f"*{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_space-{self.frameSystem}_*"))>0:
			slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes(f"*{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_space-{self.frameSystem}_*").values())[0])

		self.ui.frameFidVolumeCBox.setCurrentNode(frameFidVolume)
		frameFidVolume.SetAttribute('frameVol', '1')
		frameFidVolume.SetAttribute('regVol', '1')

		if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame')):
			shutil.rmtree(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame'))

	def getImageType(self):
		image_type='ct'

		img_data_kji = slicer.util.arrayFromVolume(self.ui.frameFidVolumeCBox.currentNode())
		if not img_data_kji.min() <-500:
			image_type='mri'

		return image_type

	def onFrameVolumeCB(self):

		if self.ui.frameFidVolumeCBox.currentNode() is None:
			return
		
		json_fname = self.ui.frameFidVolumeCBox.currentNode().GetStorageNode().GetFileName().split('.nii')[0] + '.json'

		if not os.path.exists(json_fname):
			file_attrbs = {}
			file_attrbs['source_name'] = os.path.basename(self.ui.frameFidVolumeCBox.currentNode().GetStorageNode().GetFileName())
			file_attrbs['file_name'] = os.path.basename(self.ui.frameFidVolumeCBox.currentNode().GetStorageNode().GetFileName())
			file_attrbs['node_name'] = self.ui.frameFidVolumeCBox.currentNode().GetName()
			file_attrbs['reference'] =''
			file_attrbs['window'] = self.ui.frameFidVolumeCBox.currentNode().GetDisplayNode().GetWindow()
			file_attrbs['level'] = self.ui.frameFidVolumeCBox.currentNode().GetDisplayNode().GetLevel()
			file_attrbs['coregistered'] = False
			file_attrbs['vol_type'] =''

			json_output = json.dumps(file_attrbs, indent=4)
			with open(json_fname, 'w') as fid:
				fid.write(json_output)
				fid.write('\n')

		with open(json_fname) as (file):
			self.originalFrameVolSidecar = json.load(file)
	
	def onFrameFidConfirmButton(self):

		slicer.app.setOverrideCursor(qt.Qt.WaitCursor)

		# Compute output
		progressBar = self.logic.confirmFrameDetection(self.ui.frameFidVolumeCBox.currentNode(), self.frame_settings, self.originalFrameVolSidecar, self._parameterNode.GetParameter('derivFolder'))
		
		self.ui.frameFidVolumeCBox.setCurrentNode(None)

		layoutManager = slicer.app.layoutManager()
		threeDWidget = layoutManager.threeDWidget(0)
		threeDView = threeDWidget.threeDView()
		threeDView.resetFocalPoint()
		renderer = threeDView.renderWindow().GetRenderers().GetFirstRenderer()
		renderer.SetBackground(0, 0, 0)
		renderer.SetBackground2(0, 0, 0)
		threeDView.renderWindow().Render()

		layoutManager = slicer.app.layoutManager()
		layoutManager.setLayout(slicerLayout)
		interactorStyle = slicer.app.layoutManager().sliceWidget('Red').sliceView().sliceViewInteractorStyle()
		interactorStyle.SetActionEnabled(interactorStyle.AllActionsMask, True)

		orientations = {
			'Red':'Axial', 
			'Yellow':'Sagittal', 
			'Green':'Coronal'
		}

		layoutManager = slicer.app.layoutManager()
		for sliceViewName in layoutManager.sliceViewNames():
			layoutManager.sliceWidget(sliceViewName).mrmlSliceNode().SetOrientation(orientations[sliceViewName])

		slicer.util.resetSliceViews()

		progressBar.value = 100
		slicer.app.processEvents()

		progressBar.close()
		slicer.app.restoreOverrideCursor()

	def onFrameDetectButton(self):
		"""
		**Slot for** ``Fiducial Volume`` **box.**
		
		Displays the brain scan of the patient corresponding to the 
		fiducial volume selected. 
		
		The list of available volumes:
				- 3D T1 weighted (3D-T1W)
				- Fast spin echo T2 weighted coronal view (FSEcor_T2w)
				- Fast spin echo T2 weighted transverse view (FSEtra_T2W)
				- 3D electodes T1 weighted (3DELECTRODE_T1w)
				- Fast spin echo T2 weighted saggital view (FSEsag_T2w)
				- CT scan with frame (ctFrame)
		"""

		if self.ui.frameFidVolumeCBox.currentNode() is None:
			warningBox('Please choose frame volume.')
			return
		
		if 'frame_system' not in self._parameterNode.GetParameterNames():
			warningBox('Please choose frame system.')
			return

		if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame')):
			parent = None
			for w in slicer.app.topLevelWidgets():
				if hasattr(w,'objectName'):
					if w.objectName == 'qSlicerMainWindow':
						parent=w

			windowTitle = "Frame directory exists"
			windowText = "Frame detection has already been run, would you like to re-run?"
			if parent is None:
				ret = qt.QMessageBox.question(self, windowTitle, windowText, qt.QMessageBox.Yes | qt.QMessageBox.No)
			else:
				ret = qt.QMessageBox.question(parent, windowTitle, windowText, qt.QMessageBox.Yes | qt.QMessageBox.No)
			
			if ret == qt.QMessageBox.No:
				return
			else:
				self.resetValues()
		
		os.makedirs(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame'))

		with open(self.ui.frameFidVolumeCBox.currentNode().GetStorageNode().GetFileName().split('.nii')[0] + '.json') as (file):
			self.originalFrameVolSidecar = json.load(file)

		image_type = self.getImageType()
		self.frame_settings = self.logic.selectFrameSystem(image_type, self._parameterNode.GetParameter('frame_system'))

		transforms={
			'Rigidbody (6 DOF)':0,
			'Similarity (7 DOF)':1,
			'Affine (9 DOF)':2
		}

		self.frame_settings['settings']={
			'parameters':{
				'transformType': transforms[self.ui.transformTypeCB.currentText],
				'numIterations': int(self.ui.numIterationsSB.value),
				'numLandmarks': int(self.ui.numLandmarksSB.value),
				'matchCentroids': True if self.ui.centroidMatchY.isChecked() else False,
				'distanceMetric': 'rms' if self.ui.distanceMetricRMS.isChecked() else 'abs'
			}
		}

		for k, v in self.frame_settings['settings']['parameters'].items():
			print(k + ' -> ' + str(v))

		try:

			self.framePreviousWindow = None
			self.framePreviousLevel = None
			if self.frame_settings['image_type'] == 'ct':
				self.framePreviousWindow = self.ui.frameFidVolumeCBox.currentNode().GetDisplayNode().GetWindow()
				self.framePreviousLevel = self.ui.frameFidVolumeCBox.currentNode().GetDisplayNode().GetLevel()
				self.ui.frameFidVolumeCBox.currentNode().GetDisplayNode().AutoWindowLevelOff()
				self.ui.frameFidVolumeCBox.currentNode().GetDisplayNode().SetWindow(5382)
				self.ui.frameFidVolumeCBox.currentNode().GetDisplayNode().SetLevel(-333)

			self.frame_settings['framePreviousWindow'] = self.framePreviousWindow
			self.frame_settings['framePreviousLevel'] = self.framePreviousLevel

			slicer.app.setOverrideCursor(qt.Qt.WaitCursor)

			# Compute output
			self.logic.runFrameDetection(self.ui.frameFidVolumeCBox.currentNode(), self.frame_settings, self._parameterNode.GetParameter('derivFolder'))

			slicer.app.restoreOverrideCursor()

		except AssertionError as error:
			print(error)
			slicer.util.warningDisplay('Failed to run frame detection, please ensure the correct frame model is selected.')

	def onFrameSystemButtonGroupClicked(self, button):
		"""
		Slot for ``Plot Actual Lead:`` button group under ``Left Plan``
		
		:param button: id of the button clicked
		:type button: Integer
		"""
		children = self.ui.frameSystemGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked():
				self.frameSystem = i.name
			i.checked = False

		button_idx = abs(button - -2)
		if children[button_idx].name.lower() != self.frameSystem:
			if self.frameSystem:
				children[button_idx].setChecked(True)
				self.frameSystem = []
			else:
				children[button_idx].setChecked(False)
				self.frameSystem = children[button_idx].name.lower()
		elif children[button_idx].name.lower() == self.frameSystem:
			children[button_idx].setChecked(True)
			self.frameSystem = []

	def setupNodes(self):
		markupsLogic = slicer.modules.markups.logic()
		for imark in range(self.frame_settings['n_markers']):
			imark_name=f"P{imark+1}_frame"
			self.framePointsManual[imark_name] = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			self.framePointsManual[imark_name].SetName(imark_name)
			self.framePointsManual[imark_name].GetDisplayNode().SetGlyphScale(1)
			self.framePointsManual[imark_name].GetDisplayNode().SetTextScale(4)
			self.framePointsManual[imark_name].AddDefaultStorageNode()
			self.framePointsManual[imark_name].GetStorageNode().SetCoordinateSystem(coordSys)

			self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, f"p{imark+1}FramePoint").setMRMLScene(slicer.mrmlScene)
			self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, f"p{imark+1}FramePoint").setCurrentNode(self.framePointsManual[imark_name])
			self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, f"p{imark+1}FramePoint").placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
			self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, f"p{imark+1}FramePoint").placeButton().show()
			self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, f"p{imark+1}FramePoint").deleteButton().show()

			self.uiWidget.findChild(qt.QDoubleSpinBox, f"p{imark+1}FrameX").installEventFilter(self.customEventFilter)
			self.uiWidget.findChild(qt.QDoubleSpinBox, f"p{imark+1}FrameY").installEventFilter(self.customEventFilter)
			self.uiWidget.findChild(qt.QDoubleSpinBox, f"p{imark+1}FrameZ").installEventFilter(self.customEventFilter)

	def onPointClick(self, placeWig):
		"""
		**Slot for Point 1 fiducial placement click.**
		
		Locks the point and records its coordinates.
		
		:param enabled: whether the point has been clicked onto the scan or not
		:type enabled: Boolean
		"""

		objName = placeWig.name.replace("Point","")

		rasCoord = np.zeros(3)
		placeWig.currentMarkupsFiducialNode().GetNthControlPointPositionWorld(0, rasCoord)

		self.uiWidget.findChild(qt.QDoubleSpinBox, objName + "X").value = rasCoord[0]
		self.uiWidget.findChild(qt.QDoubleSpinBox, objName + "Y").value = rasCoord[1]
		self.uiWidget.findChild(qt.QDoubleSpinBox, objName + "Z").value = rasCoord[2]
		
		placeWig.currentMarkupsFiducialNode().SetNthMarkupLocked(0, True)

	def onFrameFidButtonGroup(self, button):
		"""
		**Slot for buttons within the frame fiducial button group.**
		
		"""

		if 'Jump' in button.name:
			objName = button.name.replace("JumpButton","")
			markupsPlaceWig = self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, objName + "Point")
			markupsPlaceWig.currentMarkupsFiducialNode().SetNthMarkupLocked(0, True)
			slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(markupsPlaceWig.currentMarkupsFiducialNode().GetID(), 0)
		elif 'Lock' in button.name:
			objName = button.name.replace("LockButton","")
			markupsPlaceWig = self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, objName + "Point")

			if markupsPlaceWig.currentMarkupsFiducialNode().GetNthMarkupLocked(0):
				markupsPlaceWig.currentMarkupsFiducialNode().SetNthMarkupLocked(0, False)
				button.setStyleSheet('background-color: green')
				button.setText('Lock')
			else:
				markupsPlaceWig.currentMarkupsFiducialNode().SetNthMarkupLocked(0, True)
				button.setStyleSheet('')
				button.setText('Unlock')

		rasCoord = np.zeros(3)
		markupsPlaceWig.currentMarkupsFiducialNode().GetNthControlPointPositionWorld(0, rasCoord)

		self.uiWidget.findChild(qt.QDoubleSpinBox, objName + "X").value = rasCoord[0]
		self.uiWidget.findChild(qt.QDoubleSpinBox, objName + "Y").value = rasCoord[1]
		self.uiWidget.findChild(qt.QDoubleSpinBox, objName + "Z").value = rasCoord[2]

	def onManualDetectButton(self):
		if not self.ui.frameFiducialWig.visible:
			if self.ui.frameFidVolumeCBox.currentNode() is None:
				slicer.util.warningDisplay('Please select the image volume that contains the frame.')
				return

			if 'frame_system' not in self._parameterNode.GetParameterNames():
				warningBox('Please choose frame system.')
				return

			image_type = self.getImageType()
			self.frame_settings = self.logic.selectFrameSystem(image_type, self._parameterNode.GetParameter('frame_system'))

			self.ui.frameFiducialWig.setVisible(1)

			applicationLogic = slicer.app.applicationLogic()
			selectionNode = applicationLogic.GetSelectionNode()
			selectionNode.SetReferenceActiveVolumeID(self.ui.frameFidVolumeCBox.currentNode().GetID())
			applicationLogic.PropagateVolumeSelection(0)
			applicationLogic.FitSliceToAll()
			slicer.util.resetSliceViews()
			interactorStyle = slicer.app.layoutManager().sliceWidget("Red").sliceView().sliceViewInteractorStyle()
			interactorStyle.SetActionEnabled(interactorStyle.BrowseSlice, False)
			interactorStyle.SetActionEnabled(interactorStyle.AdjustWindowLevelBackground, True)
			layoutManager = slicer.app.layoutManager()
			layoutManager.setLayout(slicerLayoutAxial)
			layoutManager = slicer.app.layoutManager()
			layoutManager.sliceWidget('Red').mrmlSliceNode().RotateToVolumePlane(self.ui.frameFidVolumeCBox.currentNode())

			self.setupNodes()
		else:
			self.ui.frameFiducialWig.setVisible(0)

			slicer.util.resetSliceViews()
			layoutManager = slicer.app.layoutManager()
			layoutManager.setLayout(slicerLayout)
			interactorStyle = slicer.app.layoutManager().sliceWidget('Red').sliceView().sliceViewInteractorStyle()
			interactorStyle.SetActionEnabled(interactorStyle.AllActionsMask, True)

			orientations = {
				'Red':'Axial', 
				'Yellow':'Sagittal', 
				'Green':'Coronal'
			}

			layoutManager = slicer.app.layoutManager()
			for sliceViewName in layoutManager.sliceViewNames():
				layoutManager.sliceWidget(sliceViewName).mrmlSliceNode().SetOrientation(orientations[sliceViewName])

	def onShowFrameLegendButton(self):
		"""
		**Slot for** ``Show Frame Fiducial Legend`` **button.**
		
		Displays frame fiducial legend. 
		
		"""
		self.frameSystem = None
		children = self.ui.frameSystemGB.findChildren('QRadioButton')
		for i in children:
			if i.isChecked():
				self.frameSystem = i.name.lower()

		if self.frameSystem is None:
			pic_fname = 'all_fiducial_numbers.png'
			title = 'all frames'
			aspectRatio=1500
		else:
			title = self.frameSystem
			pic_fname = f'{self.frameSystem}_fiducial_numbers.png'
			aspectRatio=700

		self.pic = qt.QLabel()
		self.pic.setWindowTitle(title)
		self.pic.setScaledContents(True)
		pixmap = qt.QPixmap(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'static', pic_fname))
		#pixmap = pixmap.scaled(0.5 * pixmap.size(), qt.Qt.SmoothTransformation)
		pixmap = pixmap.scaled(aspectRatio, aspectRatio, qt.Qt.KeepAspectRatio, qt.Qt.SmoothTransformation)
		self.pic.setPixmap(pixmap)
		self.pic.frameGeometry.moveCenter(qt.QDesktopWidget().availableGeometry().center())
		self.pic.show()

	def onApplyButton(self):
		"""
		Run processing when user clicks "Apply" button.
		"""
		try:

			# Compute output
			self.logic.process(self.ui.inputSelector.currentNode(), self.ui.outputSelector.currentNode(),
				self.ui.imageThresholdSliderWidget.value, self.ui.invertOutputCheckBox.checked)

			# Compute inverted output (if needed)
			if self.ui.invertedOutputSelector.currentNode():
				# If additional output volume is selected then result with inverted threshold is written there
				self.logic.process(self.ui.inputSelector.currentNode(), self.ui.invertedOutputSelector.currentNode(),
					self.ui.imageThresholdSliderWidget.value, not self.ui.invertOutputCheckBox.checked, showResult=False)

		except Exception as e:
			slicer.util.errorDisplay("Failed to compute results: "+str(e))
			import traceback
			traceback.print_exc()


#
# frameDetectLogic
#

class frameDetectLogic(ScriptedLoadableModuleLogic):
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

		self.frameDetectInstance = None
		self.FrameAutoDetect = False

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

	def addCustomLayouts(self):

		addCustomLayouts()
		slicer.app.layoutManager().setLayout(slicerLayout)

	def selectFrameSystem(self, image_type, frameSystem):

		if 'leksellg' in frameSystem:
			frame_settings={
				'system': 'leksellg',
				'image_type':image_type,
				'min_threshold': 450,
				'max_threshold': 'n/a',
				'n_markers': 9,
				'n_components': 3,
				'min_size': 10,
				'max_size': 6500,
				'fid_lambda':80,
				'fid_ratio': 2,
				'labels':{
					1:9,2:8,3:7,4:6,5:5,6:4,7:1,8:2,9:3
				},
				'sort_idx':{
					0:[1,2,3,7,8,9],
					1:[4,5,6]
				},
				'localizer_axis':{
					'AP': [[3,2,1],[7,8,9]],
					'ML':[[4,5,6]]
				},
				'localizer_labels':{
					1:'G',2:'H',3:'I',4:'D',5:'E',6:'F',7:'A',8:'B',9:'C'
				},
				'localizer_bar_radius':4,
				'frame_mid_bars':{
					'bar_B':{
						'bot':'bar_C_bot',
						'top':'bar_A_top'
					},
					'bar_E':{
						'bot':'bar_F_bot',
						'top':'bar_D_top'
					},
					'bar_H':{
						'bot':'bar_G_bot',
						'top':'bar_I_top'
					}
				}
			}

			if image_type == 'mri':
				frame_settings['min_threshold']=400
				frame_settings['max_threshold']=1400
				frame_settings['labels']={
					1:4,2:5,3:6,4:1,5:2,6:3,7:9,8:8,9:7
				}

		elif 'leksellvantage' in frameSystem:
			frame_settings={
				'system': 'leksell vantage',
				'image_type':image_type,
				'min_threshold': 1500,
				'max_threshold': 'n/a',
				'n_markers': 6,
				'n_components': 2,
				'min_size': 100,
				'max_size': 4500,
				'fid_lambda':80,
				'fid_ratio': 2,
				'labels':{
					1:1, 2:2,  3:3,  4:4,  5:5,  6:6
				},
				'sort_idx':{
					0:[1,2,3,7,8,9]
				},
				'localizer_axis':{
					'AP': [[3,2,1],[7,8,9]],
				},
				'localizer_labels':{
					1:'G',2:'H',3:'I',7:'A',8:'B',9:'C'
				}
			}
		elif 'brw' in frameSystem:
			frame_settings={
				'system': 'brw',
				'image_type':image_type,
				'min_threshold': 200,
				'max_threshold': 460,
				'n_markers': 9,
				'n_components': 9,
				'min_size': 1000,
				'max_size': 25000,
				'fid_lambda':25,
				'fid_ratio': 10,
				'labels':{
					1:1, 2:2,  3:8,  4:5,  5:6,  6:3,  7:9,  8:7,  9:4
				},
				'sort_idx':{
					0:[1,2,3,4,5,6],
					1:[7,8,9]
				},
				'localizer_axis':{
					'AP': [[3,2,1],[6,5,4]],
					'ML':[[9,8,7]]
				},
				'localizer_labels':{
					1:'A',2:'B',3:'C',4:'D',5:'E',6:'F',7:'G',8:'H',9:'I'
				},
				'localizer_bar_radius':1,
				'frame_mid_bars':{
					'bar_B':{
						'bot':'bar_A_bot',
						'top':'bar_C_top'
					},
					'bar_E':{
						'bot':'bar_D_bot',
						'top':'bar_F_top'
					},
					'bar_H':{
						'bot':'bar_G_bot',
						'top':'bar_I_top'
					}
				}
			}
		elif 'crw' in frameSystem:
			frame_settings={
				'system': 'crw',
				'image_type':image_type,
				'min_threshold': 400,
				'max_threshold': 1300,
				'n_markers': 9,
				'n_components': 3,
				'min_size': 600,
				'max_size': 20000,
				'fid_lambda':25,
				'fid_ratio': 10,
				'labels':{
					1:9,2:8,3:7,4:6,5:5,6:4,7:1,8:2,9:3
				},
				'sort_idx':{
					0:[1,2,3,7,8,9],
					1:[4,5,6]
				},
				'localizer_axis':{
					'AP': [[3,2,1],[9,8,7]],
					'ML':[[6,5,4]]
				},
				'localizer_labels':{
					1:'G',2:'H',3:'I',4:'D',5:'E',6:'F',7:'A',8:'B',9:'C'
				},
				'localizer_bar_radius':1,
				'frame_mid_bars':{
					'bar_B':{
						'bot':'bar_A_bot',
						'top':'bar_C_top'
					},
					'bar_E':{
						'bot':'bar_D_bot',
						'top':'bar_F_top'
					},
					'bar_H':{
						'bot':'bar_G_bot',
						'top':'bar_I_top'
					}
				}
			}

		return frame_settings

	def runFrameDetection(self, frameFidVolume, frame_settings, derivFolder):
		
		applicationLogic = slicer.app.applicationLogic()
		selectionNode = applicationLogic.GetSelectionNode()
		selectionNode.SetReferenceActiveVolumeID(frameFidVolume.GetID())
		applicationLogic.PropagateVolumeSelection(0)
		applicationLogic.FitSliceToAll()
		slicer.util.resetSliceViews()
		interactionNode = applicationLogic.GetInteractionNode()
		interactionNode.Reset(None)
		layoutManager = slicer.app.layoutManager()
		layoutManager.setLayout(6)
		layoutManager = slicer.app.layoutManager()
		layoutManager.sliceWidget('Red').mrmlSliceNode().RotateToVolumePlane(frameFidVolume)
		zAxisCoordFrame = frameFidVolume.GetImageData().GetExtent()[(-1)] / 2

		self.frameDetectInstance = frameDetection(frameFidVolume, derivFolder, frame_settings)

		#jumpPoint = frameDetect.convert_ijk([170, 170, zAxisCoordFrame], self.frameFidVolume)
		
		slicer.util.getNode('vtkMRMLSliceNodeRed').JumpSliceByCentering(self.frameDetectInstance.frame_center[0], self.frameDetectInstance.frame_center[1], self.frameDetectInstance.frame_center[2])
		self.FrameAutoDetect = True

		sliceAnnotations = slicer.modules.DataProbeInstance.infoWidget.sliceAnnotations
		sliceAnnotations.sliceViewAnnotationsEnabled = False
		sliceAnnotations.updateSliceViewFromGUI()

		view = slicer.app.layoutManager().sliceWidget("Red").sliceView()
		view.cornerAnnotation().SetMaximumFontSize(20)
		if self.frameDetectInstance.meanError >0.8:
			view.cornerAnnotation().GetTextProperty().SetColor(1, 0, 0)
		else:
			view.cornerAnnotation().GetTextProperty().SetColor(0.4, 1, 0)
		view.cornerAnnotation().GetTextProperty().ShadowOff()
		view.cornerAnnotation().SetText(vtk.vtkCornerAnnotation.LeftEdge,'Mean Frame Fiducial Error: '+str(np.round(self.frameDetectInstance.meanError,3)))
		view.forceRender()

		fcsvNodeName = f"{derivFolder.split(os.path.sep)[-1]}_desc-%s_fids"

		if any(x==frame_settings['system'] for x in ('leksellg','brw','crw')):
			fidNode = slicer.util.getNode(fcsvNodeName % ('fiducials'))
			#fidNode.GetDisplayNode().GetTextProperty().SetOrientation(45.0)
			#fidNode.GetDisplayNode().SetSelectedColor(0.3, 0.6, 0.1)
			
			N1=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			N1.SetName(fcsvNodeName % ('N1'))
			N1.AddDefaultStorageNode()
			N1.GetStorageNode().SetCoordinateSystem(0)
			N1.GetDisplayNode().SetGlyphScale(0.8)
			N1.GetDisplayNode().SetTextScale(6.5)
			N1.GetDisplayNode().SetColor(0.333, 1, 0.490)
			N1.GetDisplayNode().SetSelectedColor(1, 0, 0)
			if frame_settings['system'] =='brw':
				N1_label_fmt='{val:.03f}   '
				N1.GetDisplayNode().GetTextProperty().SetJustificationToRight()
			else:
				N1_label_fmt='   {val:.03f}'
				N1.GetDisplayNode().GetTextProperty().SetJustificationToLeft()
			N1.GetDisplayNode().GetTextProperty().SetVerticalJustificationToCentered()

			N2=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			N2.SetName(fcsvNodeName % ('N2'))
			N2.AddDefaultStorageNode()
			N2.GetStorageNode().SetCoordinateSystem(0)
			N2.GetDisplayNode().SetGlyphScale(0.8)
			N2.GetDisplayNode().SetTextScale(6.5)
			N2.GetDisplayNode().SetColor(0.333, 1, 0.490)
			N2.GetDisplayNode().SetSelectedColor(1, 0, 0)
			if frame_settings['system'] =='brw':
				N2_label_fmt='   {val:.03f}'
				N2.GetDisplayNode().GetTextProperty().SetJustificationToLeft()
				N2.GetDisplayNode().GetTextProperty().SetVerticalJustificationToCentered()
			else:
				N2_label_fmt='{val:.03f}\n'
				N2.GetDisplayNode().GetTextProperty().SetJustificationToCentered()
				N2.GetDisplayNode().GetTextProperty().SetOrientation(45.0)

			N3=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			N3.SetName(fcsvNodeName % ('N3'))
			N3.AddDefaultStorageNode()
			N3.GetStorageNode().SetCoordinateSystem(0)
			N3.GetDisplayNode().SetGlyphScale(0.8)
			N3.GetDisplayNode().SetTextScale(6.5)
			N3.GetDisplayNode().SetColor(0.333, 1, 0.490)
			N3.GetDisplayNode().SetSelectedColor(1, 0, 0)
			if frame_settings['system'] =='brw':
				N3_label_fmt='{val:.03f}   '
				N3.GetDisplayNode().GetTextProperty().SetJustificationToRight()
				N3.GetDisplayNode().GetTextProperty().SetVerticalJustificationToCentered()
				N3.GetDisplayNode().GetTextProperty().SetOrientation(45.0)
			else:
				N3_label_fmt='{val:.03f}   '
				N3.GetDisplayNode().GetTextProperty().SetJustificationToRight()
				N3.GetDisplayNode().GetTextProperty().SetVerticalJustificationToCentered()

			N3Modify=N3.StartModify()
			N2Modify=N2.StartModify()
			N1Modify=N1.StartModify()

			for ifid in range(fidNode.GetNumberOfFiducials()):
				old_label = fidNode.GetNthFiducialLabel(ifid)
				position = np.zeros(3)
				fidNode.GetNthControlPointPositionWorld(ifid, position)
				node=None
				if any(x==old_label for x in ('P1','P2','P3')):
					node=N1
					new_label = N1_label_fmt.format(val=np.round(self.frameDetectInstance.pointError[ifid], 3))
				elif any(x==old_label for x in ('P4','P5','P6')):
					node=N2
					new_label = N2_label_fmt.format(val=np.round(self.frameDetectInstance.pointError[ifid], 3))
				elif any(x==old_label for x in ('P7','P8','P9')):
					node=N3
					new_label = N3_label_fmt.format(val=np.round(self.frameDetectInstance.pointError[ifid], 3))

				if node is not None:
					n = node.AddControlPoint(vtk.vtkVector3d(position[0], position[1], position[2]))
					node.SetNthControlPointLabel(n, new_label)
					node.SetNthControlPointSelected(n, 0)
					if self.frameDetectInstance.pointError[ifid] > 0.8:
						node.SetNthControlPointSelected(n, 1)

			N3.EndModify(N3Modify)
			N2.EndModify(N2Modify)
			N1.EndModify(N1Modify)
			fidNode.GetDisplayNode().SetVisibility(0)

	def confirmFrameDetection(self, frameFidVolume, frame_settings, originalFrameVolSidecar, derivFolder):

		parent = None
		for w in slicer.app.topLevelWidgets():
			if hasattr(w,'objectName'):
				if w.objectName == 'qSlicerMainWindow':
					parent=w

		# Show a progress bar
		if parent is None:
			progressBar = slicer.util.createProgressDialog(parent=self, value=0, maximum=100, windowTitle="Saving frame data...")
		else:
			progressBar = slicer.util.createProgressDialog(parent=parent, value=0, maximum=100, windowTitle="Saving frame data...")

		progressBar.show()
		slicer.app.processEvents()

		files = [x for x in os.listdir(os.path.join(derivFolder)) if any(x.endswith(y) for y in {'.nii.gz', '.nii'})]
		file_sidecar = []
		for f in files:
			with open(os.path.join(derivFolder, f.split('.nii')[0] + '.json')) as (file):
				filenames = json.load(file)
			if filenames['node_name'] == frameFidVolume.GetName():
				file_sidecar = filenames
				break

		if file_sidecar['vol_type'] != 'frame':
			file_sidecar['vol_type'] = 'frame'
			json_output = json.dumps(file_sidecar, indent=4)
			with open(os.path.join(derivFolder, frameFidVolume.GetName() + '.json'), 'w') as (fid):
				fid.write(json_output)
				fid.write('\n')
		
		frameFidVolume.SetAttribute('frame', '1')

		slicer.util.getNode('frame_center').GetDisplayNode().SetVisibility(0)

		fcsvNodeName = f"{derivFolder.split(os.path.sep)[-1]}_desc-%s_fids"
		
		slicer.mrmlScene.RemoveNode(slicer.util.getNode(fcsvNodeName % ('N1')))
		slicer.mrmlScene.RemoveNode(slicer.util.getNode(fcsvNodeName % ('N2')))
		slicer.mrmlScene.RemoveNode(slicer.util.getNode(fcsvNodeName % ('N3')))

		view=slicer.app.layoutManager().sliceWidget("Red").sliceView()
		view.cornerAnnotation().ClearAllTexts()
		view.cornerAnnotation().GetTextProperty().SetColor(1, 1, 1)
		view.cornerAnnotation().GetTextProperty().ShadowOn()
		view.forceRender()

		sliceAnnotations = slicer.modules.DataProbeInstance.infoWidget.sliceAnnotations
		sliceAnnotations.sliceViewAnnotationsEnabled=True
		sliceAnnotations.updateSliceViewFromGUI()

		if len(slicer.util.getNodes('*sourceFiducialModel*')) > 0:
			slicer.mrmlScene.RemoveNode(slicer.util.getNode('sourceFiducialModel'))
		
		if len(slicer.util.getNodes('*from-fiducials_to-localizer*')) > 0:

			progressBar.value = 15
			slicer.app.processEvents()

			frameAlignTransform = list(slicer.util.getNodes('*from-fiducials_to-localizer*').values())[0]
			frameAlignTransform.RemoveNodeReferenceIDs(slicer.vtkMRMLTransformNode.GetMovingNodeReferenceRole())
			frameAlignTransform.RemoveNodeReferenceIDs(slicer.vtkMRMLTransformNode.GetFixedNodeReferenceRole())
			slicer.util.saveNode(frameAlignTransform, os.path.join(derivFolder, 'frame', frameAlignTransform.GetName()+'.h5'))

			transformFilename = [x for x in os.listdir(os.path.join(derivFolder,'frame')) if x.endswith('.h5')][0]
			transformType = [x for x in transformFilename.split('_') if 'desc' in x][0]
			volumeType = frameFidVolume.GetName().split('_')[-1]
			origFramAcq = [x for x in frameFidVolume.GetName().split('_') if 'acq' in x]
			
			if origFramAcq:
				outputVolPrefix = f"{derivFolder.split(os.path.sep)[-1]}_space-{frame_settings['system']}_{transformType}_{origFramAcq[0]}_{volumeType}"
			else:
				outputVolPrefix = f"{derivFolder.split(os.path.sep)[-1]}_space-{frame_settings['system']}_{transformType}_{volumeType}"
			
			outputFCSVPrefix = f"{derivFolder.split(os.path.sep)[-1]}_space-{frame_settings['system']}_desc-%s_fids"
			
			with open(os.path.join(derivFolder,originalFrameVolSidecar['file_name'].split('.nii')[0] + '.json')) as (file):
				file_sidecar = json.load(file)

			slicer.vtkSlicerTransformLogic.hardenTransform(frameFidVolume)
			slicer.util.saveNode(frameFidVolume, os.path.join(derivFolder, 'frame', outputVolPrefix + '.nii.gz'))
			slicer.mrmlScene.RemoveNode(frameFidVolume)
			self.frameFidVolume = slicer.util.loadVolume(os.path.join(derivFolder, 'frame', outputVolPrefix + '.nii.gz'))
			self.frameFidVolume.SetName(outputVolPrefix)

			progressBar.value = 45
			slicer.app.processEvents()

			file_sidecar['file_name'] = outputVolPrefix + '.nii.gz'
			file_sidecar['node_name'] = outputVolPrefix
			
			file_sidecar['vol_type'] = 'frame'
			file_sidecar['frame_detection_settings']=frame_settings['settings']['parameters']

			json_output = json.dumps(file_sidecar, indent=4)
			with open(os.path.join(derivFolder, 'frame', outputVolPrefix+'.json'), 'w') as (fid):
				fid.write(json_output)
				fid.write('\n')

			#os.remove(os.path.join(derivFolder, originalFrameVolSidecar['file_name']))
			#os.remove(os.path.join(derivFolder, originalFrameVolSidecar['file_name'].split('.nii')[0] + '.json'))

			#self.ui.frameFidVolumeCBox.setCurrentNode(self.frameFidVolume)
			self.frameFidVolume.SetAttribute('frameVol', '1')
			self.frameFidVolume.SetAttribute('regVol', '1')
			
			#### save frame localizer model
			targetModelTubeName = f"{derivFolder.split(os.path.sep)[-1]}_space-{frame_settings['system']}_acq-tube_label-all_localizer"
			frameModelTubeNode = slicer.util.getNode(targetModelTubeName)
			frameModelTubeNode.GetDisplayNode().SetVisibility(0)
			
			slicer.util.saveNode(frameModelTubeNode, os.path.join(derivFolder, 'frame', targetModelTubeName +' .vtk'))

			progressBar.value = 60
			slicer.app.processEvents()

			#### remove the glyph version of the frame target
			targetModelGlyphName=f"{derivFolder.split(os.path.sep)[-1]}_space-{frame_settings['system']}_acq-glyph_label-all_localizer"
			frameModelGlyphNode = slicer.util.getNode(targetModelGlyphName)
			slicer.mrmlScene.RemoveNode(frameModelGlyphNode)

			fiducialsNode = slicer.util.getNode(fcsvNodeName % ('fiducials'))
			topbottomNode = slicer.util.getNode(fcsvNodeName % ('topbottom'))

			slicer.vtkSlicerTransformLogic.hardenTransform(topbottomNode)
			slicer.vtkSlicerTransformLogic.hardenTransform(fiducialsNode)

			fiducialsNode.SetName(outputFCSVPrefix % ('fiducials'))
			topbottomNode.SetName(outputFCSVPrefix % ('topbottom'))

			writeFCSV(fiducialsNode,os.path.join(derivFolder, 'frame', outputFCSVPrefix % ('fiducials')+'.fcsv'))
			writeFCSV(topbottomNode,os.path.join(derivFolder, 'frame', outputFCSVPrefix % ('topbottom')+'.fcsv'))

			slicer.util.getNode(outputFCSVPrefix % ('fiducials')).GetDisplayNode().SetVisibility(0)
			slicer.util.getNode(outputFCSVPrefix % ('topbottom')).GetDisplayNode().SetVisibility(0)

			progressBar.value = 70
			slicer.app.processEvents()

			if frame_settings['system'] != 'brw':
				frameFiducialPoints={}
				frameFiducialPoints['label']=[int(x) for x in self.frameDetectInstance.final_location_clusters[:,3]]
				frameFiducialPoints['x']=[format (x, '.3f') for x in self.frameDetectInstance.final_location_clusters[:,0]]
				frameFiducialPoints['y']=[format (x, '.3f') for x in self.frameDetectInstance.final_location_clusters[:,1]]
				frameFiducialPoints['z']=[format (x, '.3f') for x in self.frameDetectInstance.final_location_clusters[:,2]]
				frameFiducialPoints['intensity']=[format (x, '.3f') for x in self.frameDetectInstance.final_location_clusters[:,4]]
				
				outfile_name = os.path.join(derivFolder, 'frame',
					f"{derivFolder.split(os.path.sep)[-1]}_space-{frame_settings['system']}_desc-clusters_fids.tsv")
				
				with open(outfile_name, 'w') as out_file:
					writer = csv.writer(out_file, delimiter = "\t")
					writer.writerow(frameFiducialPoints.keys())
					writer.writerows(zip(*frameFiducialPoints.values()))

			frameFiducialPoints={}
			frameFiducialPoints['label']=[int(x) for x in self.frameDetectInstance.final_location[:,3]]
			frameFiducialPoints['x']=[format (x, '.3f') for x in self.frameDetectInstance.sourcePoints[:,0]]
			frameFiducialPoints['y']=[format (x, '.3f') for x in self.frameDetectInstance.sourcePoints[:,1]]
			frameFiducialPoints['z']=[format (x, '.3f') for x in self.frameDetectInstance.sourcePoints[:,2]]
			frameFiducialPoints['intensity']=[format (x, '.3f') for x in self.frameDetectInstance.final_location[:,4]]
			frameFiducialPoints['error']=[format (x, '.3f') for x in self.frameDetectInstance.pointError]
			frameFiducialPoints['dist_x']=[format (x, '.3f') for x in self.frameDetectInstance.pointDistanceXYZ[:,0]]
			frameFiducialPoints['dist_y']=[format (x, '.3f') for x in self.frameDetectInstance.pointDistanceXYZ[:,1]]
			frameFiducialPoints['dist_z']=[format (x, '.3f') for x in self.frameDetectInstance.pointDistanceXYZ[:,2]]
			frameFiducialPoints['n_cluster']=[int(x) for x in self.frameDetectInstance.final_location[:,-1]]
			frameFiducialPoints['ideal_x']=[format (x, '.3f') for x in self.frameDetectInstance.idealPoints[:,0]]
			frameFiducialPoints['ideal_y']=[format (x, '.3f') for x in self.frameDetectInstance.idealPoints[:,1]]
			frameFiducialPoints['ideal_z']=[format (x, '.3f') for x in self.frameDetectInstance.idealPoints[:,2]]

			outfile_name = os.path.join(derivFolder, 'frame',
				f"{derivFolder.split(os.path.sep)[-1]}_space-{frame_settings['system']}_desc-centroids_fids.tsv")
			
			progressBar.value = 80
			slicer.app.processEvents()

			with open(outfile_name, 'w') as out_file:
				writer = csv.writer(out_file, delimiter = "\t")
				writer.writerow(frameFiducialPoints.keys())
				writer.writerows(zip(*frameFiducialPoints.values()))

			if len(slicer.util.getNodes('*frame_center*')) > 0:
				frameCenterNode=list(slicer.util.getNodes('*frame_center*').values())[0]
				slicer.vtkSlicerTransformLogic.hardenTransform(frameCenterNode)
				frameCenterNode.GetDisplayNode().SetVisibility(0)
			
			slicer.mrmlScene.RemoveNode(frameAlignTransform)
		else:
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if f"space-{frame_settings['system']}_label-" in imodel.GetName():
					if 'label-all' in imodel.GetName():
						slicer.util.getNode(imodel.GetID()).GetDisplayNode().SetVisibility(0)
					else:
						slicer.mrmlScene.RemoveNode(imodel)

		if frame_settings['framePreviousWindow'] is not None and frame_settings['framePreviousLevel'] is not None:
			self.frameFidVolume.GetDisplayNode().SetWindow(frame_settings['framePreviousWindow'])
			self.frameFidVolume.GetDisplayNode().SetLevel(frame_settings['framePreviousLevel'])
		
		if not os.path.exists(os.path.join(derivFolder, f"{derivFolder.split(os.path.sep)[-1]}_surgical_data.json")):
			surgical_info_json = {}
			surgical_info_json['subject'] = derivFolder.split(os.path.sep)[-1].split(os.path.sep)[-1]
			surgical_info_json['surgery_date'] = []
			surgical_info_json['surgeon'] = []
			surgical_info_json['target'] = []
			surgical_info_json['frame_system'] = []
			surgical_info_json['trajectories'] = {}
			
			json_output = json.dumps(surgical_info_dict(surgical_info_json), indent=4)
			with open(os.path.join(derivFolder, f"{derivFolder.split(os.path.sep)[-1].split(os.path.sep)[-1]}_surgical_data.json"),'w') as fid:
				fid.write(json_output)
				fid.write('\n')

		progressBar.value = 85
		slicer.app.processEvents()

		with open(os.path.join(derivFolder, f"{derivFolder.split(os.path.sep)[-1]}_surgical_data.json")) as (surgical_file):
			surgical_data = json.load(surgical_file)

		surgical_data['frame_system'] = frame_settings['system']

		json_output = json.dumps(surgical_data, indent=4)
		with open(os.path.join(derivFolder, f"{derivFolder.split(os.path.sep)[-1]}_surgical_data.json"), 'w') as (fid):
			fid.write(json_output)
			fid.write('\n')

		progressBar.value = 90
		slicer.app.processEvents()

		return progressBar

#
# frameDetectTest
#

class frameDetectTest(ScriptedLoadableModuleTest):
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
		self.test_frameDetect1()

	def test_frameDetect1(self):
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
		inputVolume = SampleData.downloadSample('frameDetect1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = frameDetectLogic()

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
