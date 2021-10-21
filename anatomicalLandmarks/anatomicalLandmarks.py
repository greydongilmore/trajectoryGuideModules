import os
import sys
import shutil
import numpy as np
import json
import collections
import vtk, qt, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

if getattr(sys, 'frozen', False):
	cwd = os.path.dirname(sys.argv[0])
elif __file__:
	cwd = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(1, os.path.dirname(cwd))

from helpers.helpers import warningBox, addCustomLayouts,adjustPrecision,getPointCoords,getMarkupsNode,getFrameCenter
from helpers.variables import coordSys, fontSetting, slicerLayout, groupboxStyle

#
# anatomicalLandmarks
#

class anatomicalLandmarks(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "04: Anatomical Landmarks"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = ["dataImport"]
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#anatomicalLandmarks">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# anatomicalLandmarksWidget
#

class anatomicalLandmarksWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
		self.crossHairLastPosition = collections.deque(maxlen=2)
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
		self.logic = anatomicalLandmarksLogic()

		self.setupMarkupNodes()

		# Connections
		self._setupConnections()

	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/anatomicalLandmarks.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)

		self.ui.acpcTransformCBox.setMRMLScene(slicer.mrmlScene)
		self.ui.acpcTransformCBox.addAttribute('vtkMRMLLinearTransformNode', 'acpc', '1')

		self.text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
		fontSettings = qt.QFont(fontSetting)
		fontSettings.setBold(False)
		self.ui.runACPCTransformGB.setStyleSheet(groupboxStyle + f"color: {self.text_color}" + '}')
		self.ui.runACPCTransformGB.setFont(fontSettings)
		self.ui.mcpWig.setVisible(0)
		self.ui.mid3Wig.setVisible(0)
		self.ui.mid4Wig.setVisible(0)
		self.ui.mid5Wig.setVisible(0)

	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).

		self.crosshairNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLCrosshairNode')
		self.crosshairNode.AddObserver(slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent, self.onCursorPositionModifiedEvent)

		self.ui.crosshairUpdateFrameButton.clicked.connect(lambda : self.onUpdateCrosshairFrame(True))

		#self.ui.midlineFidButtonGroup.buttonClicked.connect(self.onButtonClick)
		self.ui.fidButtonGroup.buttonClicked.connect(self.onButtonClick)
		self.ui.addMidButton.connect('clicked(bool)', self.onAddMidlineButton)
		self.ui.removeMidButton.connect('clicked(bool)', self.onRemoveMidlineButton)
		self.ui.fidConfirmButton.connect('clicked(bool)', self.onFidConfirmButton)
		self.ui.acpcTransformButton.connect('clicked(bool)', self.onAcpcTransformButton)
		self.ui.acpcTransformDelete.connect('clicked(bool)', self.onAcpcTransformDeleteButton)
		self.ui.acpcTransformCBox.connect('currentNodeChanged(bool)', self.onACPCTransformCBox)
		
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
		if self._parameterNode.GetParameter('derivFolder'):
			self.markupsLogic = slicer.modules.markups.logic()
			if len(slicer.util.getNodes('acpc')) > 0:
				fiducialNode = getMarkupsNode('acpc')
				for ifid in range(fiducialNode.GetNumberOfControlPoints()):
					fidLabel = fiducialNode.GetNthControlPointLabel(ifid)
					fidX = self.uiWidget.findChild(qt.QDoubleSpinBox, f'{fidLabel}X')
					fidY = self.uiWidget.findChild(qt.QDoubleSpinBox, f'{fidLabel}Y')
					fidZ = self.uiWidget.findChild(qt.QDoubleSpinBox, f'{fidLabel}Z')
					if all(x is not None for x in (fidX, fidY, fidZ)):
						pointCoordsWorld = np.zeros(3)
						fiducialNode.GetNthControlPointPositionWorld(ifid, pointCoordsWorld)
						
						fidX.value = pointCoordsWorld[0]
						fidY.value = pointCoordsWorld[1]
						fidZ.value = pointCoordsWorld[2]
						
						markupsNode = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
						markupsNode.SetName(fidLabel)
						markupsNode.AddDefaultStorageNode()

						pointNode = self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, f'{fidLabel}Point')
						pointNode.setCurrentNode(markupsNode)

						if 'mcp' in fidLabel:
							self.ui.mcpWig.setVisible(1)
			else:
				if len(slicer.util.getNodes('ac')) == 0:
					self.markupsNodeAC = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
					self.markupsNodeAC.SetName('ac')
					self.markupsNodeAC.AddDefaultStorageNode()
					self.markupsNodeAC.GetStorageNode().SetCoordinateSystem(coordSys)
					self.ui.acPoint.setCurrentNode(self.markupsNodeAC)

					self.markupsNodeAC.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
					#self.markupsNodeAC.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)
				
				if len(slicer.util.getNodes('pc')) == 0:
					self.markupsNodePC = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
					self.markupsNodePC.SetName('pc')
					self.markupsNodePC.AddDefaultStorageNode()
					self.markupsNodePC.GetStorageNode().SetCoordinateSystem(coordSys)
					self.ui.pcPoint.setCurrentNode(self.markupsNodePC)

					self.markupsNodePC.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
					#self.markupsNodePC.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)
				
				if len(slicer.util.getNodes('mcp')) == 0:
					self.markupsNodeMCP = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
					self.markupsNodeMCP.SetName('mcp')
					self.markupsNodeMCP.AddDefaultStorageNode()
					self.markupsNodeMCP.GetStorageNode().SetCoordinateSystem(coordSys)
					self.ui.mcpPoint.setCurrentNode(self.markupsNodeMCP)

					self.markupsNodeMCP.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
					#self.markupsNodeMCP.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)
			
			if len(slicer.util.getNodes('midline')) > 0:
				midlineNode = getMarkupsNode('midline')
				for ifid in range(midlineNode.GetNumberOfControlPoints()):
					fidLabel = midlineNode.GetNthControlPointLabel(ifid)
					fidX = self.uiWidget.findChild(qt.QDoubleSpinBox, f'{fidLabel}X')
					fidY = self.uiWidget.findChild(qt.QDoubleSpinBox, f'{fidLabel}Y')
					fidZ = self.uiWidget.findChild(qt.QDoubleSpinBox, f'{fidLabel}Z')
					if all(x is not None for x in (fidX, fidY, fidZ)):
						pointCoordsWorld = np.zeros(3)
						midlineNode.GetNthControlPointPositionWorld(ifid, pointCoordsWorld)
						
						fidX.value = pointCoordsWorld[0]
						fidY.value = pointCoordsWorld[1]
						fidZ.value = pointCoordsWorld[2]

						markupsNode = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
						markupsNode.SetName(fidLabel)
						markupsNode.AddDefaultStorageNode()

						pointNode = self.uiWidget.findChild(slicer.qSlicerMarkupsPlaceWidget, f'{fidLabel}Point')
						pointNode.setCurrentNode(markupsNode)
			else:
				self.markupsLogic = slicer.modules.markups.logic()
				if len(slicer.util.getNodes('mid1')) == 0:
					self.markupsNodeMid1 = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
					self.markupsNodeMid1.SetName('mid1')
					self.markupsNodeMid1.AddDefaultStorageNode()
					self.markupsNodeMid1.GetStorageNode().SetCoordinateSystem(coordSys)
					self.ui.mid1Point.setCurrentNode(self.markupsNodeMid1)

					self.markupsNodeMid1.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
					#self.markupsNodeMid1.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)
				
				if len(slicer.util.getNodes('mid2')) == 0:
					self.markupsNodeMid2 = slicer.mrmlScene.GetNodeByID(self.markupsLogic.AddNewFiducialNode())
					self.markupsNodeMid2.SetName('mid2')
					self.markupsNodeMid2.AddDefaultStorageNode()
					self.markupsNodeMid2.GetStorageNode().SetCoordinateSystem(coordSys)
					self.ui.mid2Point.setCurrentNode(self.markupsNodeMid2)

					self.markupsNodeMid2.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
					#self.markupsNodeMid2.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)

	def exit(self):
		"""
		Called each time the user opens a different module.
		"""
		# Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
		self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
		for imarkup in ('ac','pc','mcp','mid1','mid2'):
			if len(slicer.util.getNodes(imarkup)) > 0:
				if not slicer.util.getNode(imarkup).GetNumberOfControlPoints() >0:
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(imarkup))

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

		wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

		if self.ui.frameFidVolumeCBox.currentNode() is not None:
			derivFolder = os.path.dirname(self.ui.frameFidVolumeCBox.currentNode().GetStorageNode().GetFileName())
			self._parameterNode.SetParameter("derivFolder", derivFolder)

		if isinstance(caller, qt.QRadioButton):
			print(caller.name)
			self._parameterNode.SetParameter("frame_system", caller.name)

		self._parameterNode.EndModify(wasModified)

	def setupMarkupNodes(self):
		self.ui.acPoint.setMRMLScene(slicer.mrmlScene)
		self.ui.acPoint.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.acPoint.placeButton().show()
		#self.ui.acPoint.deleteButton().show()

		self.ui.pcPoint.setMRMLScene(slicer.mrmlScene)
		self.ui.pcPoint.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.pcPoint.placeButton().show()
		#self.ui.pcPoint.deleteButton().show()

		self.ui.mcpPoint.setMRMLScene(slicer.mrmlScene)
		self.ui.mcpPoint.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.mcpPoint.placeButton().show()
		#self.ui.mcpPoint.deleteButton().show()
		
		self.ui.mid1Point.setMRMLScene(slicer.mrmlScene)
		self.ui.mid1Point.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.mid1Point.placeButton().show()
		#self.ui.mid1Point.deleteButton().show()
		
		self.ui.mid2Point.setMRMLScene(slicer.mrmlScene)
		self.ui.mid2Point.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.mid2Point.placeButton().show()
		#self.ui.mid2Point.deleteButton().show()
		
		self.ui.mid3Point.setMRMLScene(slicer.mrmlScene)
		self.ui.mid3Point.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.mid3Point.placeButton().show()
		#self.ui.mid3Point.deleteButton().show()
		
		self.ui.mid4Point.setMRMLScene(slicer.mrmlScene)
		self.ui.mid4Point.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.mid4Point.placeButton().show()
		#self.ui.mid4Point.deleteButton().show()
		
		self.ui.mid5Point.setMRMLScene(slicer.mrmlScene)
		self.ui.mid5Point.placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
		self.ui.mid5Point.placeButton().show()
		#self.ui.mid5Point.deleteButton().show()

	def adjustPrecision(self, vector):
		if isinstance(vector, float):
			out = np.round(vector, self.num_precision)
		else:
			out = np.array(np.round(vector, self.num_precision))
		return out

	def onPointAdd(self, caller, event):
		activeLabel = caller.GetName().split('-')[0]
		fidPresent = False
		movingMarkupIndex = caller.GetDisplayNode().GetActiveControlPoint()
		for ifid in range(caller.GetNumberOfControlPoints()):
			if activeLabel in caller.GetNthControlPointLabel(ifid):
				activePointCoords = np.zeros(3)
				caller.GetNthControlPointPositionWorld(ifid, activePointCoords)
				fidPresent=True
		
		if fidPresent:
			caller.RemoveAllControlPoints()

		if any(x in activeLabel for x in {'ac', 'mcp', 'pc'}):
			fidName = 'acpc'
		else:
			fidName = 'midline'

		fidPresent=False
		fiducialNode = getMarkupsNode(fidName, create=True)
		if fiducialNode is not None:
			for ifid in range(fiducialNode.GetNumberOfControlPoints()):
				if activeLabel in fiducialNode.GetNthControlPointLabel(ifid):
					fiducialNode.SetNthControlPointPositionWorld(ifid, activePointCoords[0], activePointCoords[1], activePointCoords[2])
					fidPresent=True
		
		if not fidPresent:
			n = fiducialNode.AddControlPointWorld(vtk.vtkVector3d(activePointCoords[0], activePointCoords[1], activePointCoords[2]))
			fiducialNode.SetNthControlPointLabel(n, activeLabel)
			fiducialNode.SetNthControlPointLocked(n, True)

		if 'ac' in activeLabel:
			self.ui.acX.value = activePointCoords[0]
			self.ui.acY.value = activePointCoords[1]
			self.ui.acZ.value = activePointCoords[2]
		elif 'pc' in activeLabel:
			self.ui.pcX.value = activePointCoords[0]
			self.ui.pcY.value = activePointCoords[1]
			self.ui.pcZ.value = activePointCoords[2]
		elif 'mcp' in activeLabel:
			self.ui.mcpX.value = activePointCoords[0]
			self.ui.mcpY.value = activePointCoords[1]
			self.ui.mcpZ.value = activePointCoords[2]
		elif 'mid1' in activeLabel:
			self.ui.mid1X.value = activePointCoords[0]
			self.ui.mid1Y.value = activePointCoords[1]
			self.ui.mid1Z.value = activePointCoords[2]
		elif 'mid2' in activeLabel:
			self.ui.mid2X.value = activePointCoords[0]
			self.ui.mid2Y.value = activePointCoords[1]
			self.ui.mid2Z.value = activePointCoords[2]
		elif 'mid3' in activeLabel:
			self.ui.mid3X.value = activePointCoords[0]
			self.ui.mid3Y.value = activePointCoords[1]
			self.ui.mid3Z.value = activePointCoords[2]
		elif 'mid4' in activeLabel:
			self.ui.mid4X.value = activePointCoords[0]
			self.ui.mid4Y.value = activePointCoords[1]
			self.ui.mid4Z.value = activePointCoords[2]
		elif 'mid5' in activeLabel:
			self.ui.mid5X.value = activePointCoords[0]
			self.ui.mid5Y.value = activePointCoords[1]
			self.ui.mid5Z.value = activePointCoords[2]

	def onButtonClick(self, button):

		fiducialPoint = button.name.replace('JumpButton', '').replace('LockButton', '').replace('DelButton', '').replace('PointsVisOFF', '')
		pointNode = None
		fidNodeName=None
		fiducialPointRAS = getPointCoords(fiducialPoint, fiducialPoint)

		if not np.array_equal(adjustPrecision(fiducialPointRAS), adjustPrecision(np.zeros(3))):
			fidNodeName=fiducialPoint
			pointNode = getMarkupsNode(fiducialPoint)
		
		if pointNode is None:
			if any(x in fiducialPoint for x in {'ac', 'mcp', 'pc'}):
				fidNodeName = 'acpc'
			else:
				fidNodeName = 'midline'

			fiducialPointRAS = getPointCoords(fidNodeName, fiducialPoint)

			if not np.array_equal(adjustPrecision(fiducialPointRAS), adjustPrecision(np.zeros(3))):
				pointNode = getMarkupsNode(fidNodeName)

		if 'LockButton' in button.name:
			pointLocked = True
			pointExists = False
			fiducialNode = getMarkupsNode(fidNodeName)
			for ifid in range(fiducialNode.GetNumberOfControlPoints()):
				if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
					pointExists = True
				if fiducialNode.GetNthControlPointLocked(ifid) == 1 and pointExists:
					fiducialNode.SetNthControlPointLocked(ifid, False)
					pointLocked = False
					button.setStyleSheet('background-color: green')
					button.setText('Lock')
					fiducialNode.GetDisplayNode().SetVisibility(1)

			if not pointExists:
				warningBox(f"No fiducial defined for {fiducialPoint}, please set a point.")
				return

			if any(x in fiducialPoint for x in {'ac', 'mcp', 'pc'}):
				fidName = 'acpc'
			else:
				fidName = 'midline'
			
			if pointExists:
				if pointLocked:
					button.setStyleSheet('')
					button.setText('Unlock')
					
					fiducialNode = getMarkupsNode(fidName)
					if fiducialNode is not None:
						for ifid in range(fiducialNode.GetNumberOfControlPoints()):
							if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
								fiducialNode.SetNthControlPointPositionWorld(ifid, fiducialPointRAS[0], fiducialPointRAS[1], fiducialPointRAS[2])
								fiducialNode.SetNthControlPointVisibility(ifid, 1)
								fiducialNode.SetNthControlPointLocked(ifid, True)

						if 'ac' in fiducialPoint:
							self.ui.acX.value = fiducialPointRAS[0]
							self.ui.acY.value = fiducialPointRAS[1]
							self.ui.acZ.value = fiducialPointRAS[2]
						elif 'pc' in fiducialPoint:
							self.ui.pcX.value = fiducialPointRAS[0]
							self.ui.pcY.value = fiducialPointRAS[1]
							self.ui.pcZ.value = fiducialPointRAS[2]
						elif 'mcp' in fiducialPoint:
							self.ui.mcpX.value = fiducialPointRAS[0]
							self.ui.mcpY.value = fiducialPointRAS[1]
							self.ui.mcpZ.value = fiducialPointRAS[2]
						elif 'mid1' in fiducialPoint:
							self.ui.mid1X.value = fiducialPointRAS[0]
							self.ui.mid1Y.value = fiducialPointRAS[1]
							self.ui.mid1Z.value = fiducialPointRAS[2]
						elif 'mid2' in fiducialPoint:
							self.ui.mid2X.value = fiducialPointRAS[0]
							self.ui.mid2Y.value = fiducialPointRAS[1]
							self.ui.mid2Z.value = fiducialPointRAS[2]
						elif 'mid3' in fiducialPoint:
							self.ui.mid3X.value = fiducialPointRAS[0]
							self.ui.mid3Y.value = fiducialPointRAS[1]
							self.ui.mid3Z.value = fiducialPointRAS[2]
						elif 'mid4' in fiducialPoint:
							self.ui.mid4X.value = fiducialPointRAS[0]
							self.ui.mid4Y.value = fiducialPointRAS[1]
							self.ui.mid4Z.value = fiducialPointRAS[2]
						elif 'mid5' in fiducialPoint:
							self.ui.mid5X.value = fiducialPointRAS[0]
							self.ui.mid5Y.value = fiducialPointRAS[1]
							self.ui.mid5Z.value = fiducialPointRAS[2]
		
		elif 'DelButton' in button.name:
			fiducialNode = getMarkupsNode(fiducialPoint)
			fidPresent=False
			for ifid in range(fiducialNode.GetNumberOfControlPoints()):
				if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
					fidPresent=True

			if fidPresent:
				fiducialNode.RemoveAllControlPoints()

			fiducialNode.GetDisplayNode().SetVisibility(1)
			if any(x in fiducialPoint for x in {'ac', 'mcp', 'pc'}):
				fidName = 'acpc'
			else:
				fidName = 'midline'

			fiducialNode = getMarkupsNode(fidName)
			if fiducialNode is not None:
				for ifid in range(fiducialNode.GetNumberOfControlPoints()):
					if fiducialPoint in fiducialNode.GetNthControlPointLabel(ifid):
						fiducialNode.RemoveNthControlPoint(ifid)

			if 'ac' in fiducialPoint:
				self.ui.acX.value = 0
				self.ui.acY.value = 0
				self.ui.acZ.value = 0
			elif 'pc' in fiducialPoint:
				self.ui.pcX.value = 0
				self.ui.pcY.value = 0
				self.ui.pcZ.value = 0
			elif 'mcp' in fiducialPoint:
				self.ui.mcpX.value = 0
				self.ui.mcpY.value = 0
				self.ui.mcpZ.value = 0
			elif 'mid1' in fiducialPoint:
				self.ui.mid1X.value = 0
				self.ui.mid1Y.value = 0
				self.ui.mid1Z.value = 0
			elif 'mid2' in fiducialPoint:
				self.ui.mid2X.value = 0
				self.ui.mid2Y.value = 0
				self.ui.mid2Z.value = 0
			elif 'mid3' in fiducialPoint:
				self.ui.mid3X.value = 0
				self.ui.mid3Y.value = 0
				self.ui.mid3Z.value = 0
			elif 'mid4' in fiducialPoint:
				self.ui.mid4X.value = 0
				self.ui.mid4Y.value = 0
				self.ui.mid4Z.value = 0
			elif 'mid5' in fiducialPoint:
				self.ui.mid5X.value = 0
				self.ui.mid5Y.value = 0
				self.ui.mid5Z.value = 0

		elif 'JumpButton' in button.name:
			
			if pointNode is not None:
				for ifid in range(pointNode.GetNumberOfControlPoints()):
					if fiducialPoint in pointNode.GetNthControlPointLabel(ifid):
						crossCoordsWorld = np.zeros(3)
						pointNode.GetNthControlPointPositionWorld(ifid, crossCoordsWorld)

						for islice in ('Red','Green','Yellow'):
							sliceNode = slicer.app.layoutManager().sliceWidget(islice).mrmlSliceNode().JumpSliceByCentering(crossCoordsWorld[0], crossCoordsWorld[1], crossCoordsWorld[2])

						crossHairPlanningNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLCrosshairNode')
						crossHairPlanningNode.SetCrosshairRAS(vtk.vtkVector3d(crossCoordsWorld[0], crossCoordsWorld[1], crossCoordsWorld[2]))

						self.crossHairLastPosition.append(np.array(crossCoordsWorld))
			else:
				warningBox(f"No fiducial defined for {fiducialPoint}, please set a point.")
				return

		elif 'PointsVis' in button.name:
			markupNodes = slicer.util.getNodesByClass('vtkMRMLMarkupsFiducialNode')

			for ifid in markupNodes:
				if fiducialPoint.lower() in ifid.GetName():
					if button.text == 'ON':
						ifid.GetDisplayNode().SetVisibility(1)
					else:
						ifid.GetDisplayNode().SetVisibility(0)

	def onAddMidlineButton(self):
		"""
		Slot for ``Add Midline`` button.
		"""
		if not self.ui.mid3Wig.visible:
			self.ui.mid3Wig.setVisible(1)
			self.markupsNodeMid3 = slicer.mrmlScene.GetNodeByID(slicer.modules.markups.logic().AddNewFiducialNode())
			self.markupsNodeMid3.SetName('mid3')
			self.markupsNodeMid3.AddDefaultStorageNode()
			self.markupsNodeMid3.GetStorageNode().SetCoordinateSystem(coordSys)
			self.ui.mid3Point.setCurrentNode(self.markupsNodeMid3)

			self.markupsNodeMid3.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
			#self.markupsNodeMid3.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)

		elif not self.ui.mid4Wig.visible:
			self.ui.mid4Wig.setVisible(1)
			self.markupsNodeMid4 = slicer.mrmlScene.GetNodeByID(slicer.modules.markups.logic().AddNewFiducialNode())
			self.markupsNodeMid4.SetName('mid4')
			self.markupsNodeMid4.AddDefaultStorageNode()
			self.markupsNodeMid4.GetStorageNode().SetCoordinateSystem(coordSys)
			#self.ui.mid4Point.setCurrentNode(self.markupsNodeMid4)

			self.markupsNodeMid4.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
			#self.markupsNodeMid4.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)
		elif not self.ui.mid5Wig.visible:
			self.ui.mid5Wig.setVisible(1)
			self.markupsNodeMid5 = slicer.mrmlScene.GetNodeByID(slicer.modules.markups.logic().AddNewFiducialNode())
			self.markupsNodeMid5.SetName('mid5')
			self.markupsNodeMid5.AddDefaultStorageNode()
			self.markupsNodeMid5.GetStorageNode().SetCoordinateSystem(coordSys)
			self.ui.mid5Point.setCurrentNode(self.markupsNodeMid5)

			self.markupsNodeMid5.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onPointAdd)
			#self.markupsNodeMid5.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionUndefinedEvent, self.onPointDelete)

	def onCursorPositionModifiedEvent(self, caller=None, event=None):
		if self.active:
			if self._parameterNode.GetNodeReference('frame_system') and caller.GetCrosshairMode() == 1:
				cursorRAS = np.zeros(3)
				self.crosshairNode.GetCursorPositionRAS(cursorRAS)
				crossHairRAS = np.array(self.crosshairNode.GetCrosshairRAS())
				self.crossHairLastPosition.append(cursorRAS.copy())
				if np.array_equal(adjustPrecision(crossHairRAS), adjustPrecision(self.crossHairLastPosition[0])):
					crossHairRAS = np.array(self.crosshairNode.GetCrosshairRAS())

					fc = getFrameCenter(self._parameterNode.GetParameter('frame_system'))
					if fc is not None:
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
							coordsFrame=np.dot(frameToRAS, np.append(coordsFrame,1))[:3]
						else:
							coordsFrame=crossHairRAS-fc
						
						self.ui.frameCoordsX.value = coordsFrame[0]
						self.ui.frameCoordsY.value = coordsFrame[1]
						self.ui.frameCoordsZ.value = coordsFrame[2]

	def onUpdateCrosshairFrame(self, button):
		"""
		Slot for ``Update Crosshairs`` button
		"""
		if self._parameterNode.GetParameter('frame_system'):
			coordsFrame = np.array([self.ui.frameCoordsX.value, self.ui.frameCoordsY.value, self.ui.frameCoordsZ.value])

			fc = getFrameCenter(self._parameterNode.GetParameter('frame_system'))
			print(self._parameterNode.GetParameter('frame_system'))
			if 'leksell' in self._parameterNode.GetParameter('frame_system'):
				frameToRAS = np.array([
					[ -1, 0, 0, 100],
					[  0, 1, 0,-100],
					[  0, 0,-1, 100],
					[  0, 0, 0,   1]
				])
				coordsRAS=np.dot(frameToRAS, np.append(coordsFrame,1))[:3]
				RASToFrame = np.array([
					[ 1, 0, 0, fc[0]],
					[ 0, 1, 0, fc[1]],
					[ 0, 0, 1, fc[2]],
					[ 0, 0, 0,   1]
				])
				coordsRAS=np.dot(RASToFrame, np.append(coordsRAS,1))[:3]
			else:
				RASToFrame = np.array([
					[ 1, 0, 0, fc[0]],
					[ 0, 1, 0, fc[1]],
					[ 0, 0, 1, fc[2]],
					[ 0, 0, 0,   1]
				])
				coordsRAS=np.dot(RASToFrame, np.append(coordsFrame,1))[:3]

			self.crosshairNode.SetCrosshairRAS(vtk.vtkVector3d(coordsRAS[0], coordsRAS[1], coordsRAS[2]))
			sliceNodes = slicer.util.getNodesByClass('vtkMRMLSliceNode')
			for islice in sliceNodes:
				islice.JumpSlice(coordsRAS[0], coordsRAS[1], coordsRAS[2])

	def onRemoveMidlineButton(self):
		"""
		Slot for ``Remove Midline`` button.
		"""
		if self.ui.mid5Wig.visible:
			self.ui.mid5Wig.setVisible(0)
			slicer.mrmlScene.RemoveNode(slicer.util.getNode('mid5'))
			self.markupsNodeMid5.RemoveAllObservers()
		elif self.ui.mid4Wig.visible:
			self.ui.mid4Wig.setVisible(0)
			slicer.mrmlScene.RemoveNode(slicer.util.getNode('mid4'))
			self.markupsNodeMid4.RemoveAllObservers()
		elif self.ui.mid3Wig.visible:
			self.ui.mid3Wig.setVisible(0)
			slicer.mrmlScene.RemoveNode(slicer.util.getNode('mid3'))
			self.markupsNodeMid3.RemoveAllObservers()

	def onFidConfirmButton(self):
		"""
		Slot for ``Confirm Fiducials`` button.
		"""
		if 'acpc' not in slicer.util.getNodes():
			fidNodeACPC = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			if slicer.util.getNode('ac').GetTransformNodeID() is not None:
				fidNodeACPC.SetAndObserveTransformNodeID(slicer.util.getNode('ac').GetTransformNodeID())
			fidNodeACPC.SetName('acpc')
			fidNodeACPC.AddDefaultStorageNode()
			fidNodeACPC.GetStorageNode().SetCoordinateSystem(coordSys)

			rasCoordAC = getPointCoords('ac', 'ac')
			rasCoordPC = getPointCoords('pc', 'pc')
		else:
			fidNodeACPC = getMarkupsNode('acpc')
			rasCoordAC = getPointCoords('acpc', 'ac')
			rasCoordPC = getPointCoords('acpc', 'pc')

		
		rasCoordMCP = [(rasCoordAC[0] + rasCoordPC[0]) / 2, (rasCoordAC[1] + rasCoordPC[1]) / 2, (rasCoordAC[2] + rasCoordPC[2]) / 2]

		self.ui.mcpWig.setVisible(1)
		self.ui.mcpX.value = rasCoordMCP[0]
		self.ui.mcpY.value = rasCoordMCP[1]
		self.ui.mcpZ.value = rasCoordMCP[2]

		for iacpc in ('ac', 'pc', 'mcp'):
			fidCoordsSingle=getPointCoords(iacpc, iacpc)
			fidCoordsACPC=getPointCoords('acpc', iacpc)

			if not np.array_equal(adjustPrecision(fidCoordsSingle), adjustPrecision(np.zeros(3))):
				if not np.array_equal(adjustPrecision(fidCoordsSingle), adjustPrecision(fidCoordsACPC)):
					nodePresent=False
					for ifid in range(fidNodeACPC.GetNumberOfControlPoints()):
						if iacpc in fidNodeACPC.GetNthControlPointLabel(ifid):
							nodePresent=True
							fidNodeACPC.SetNthControlPointPositionWorld(ifid, fidCoordsSingle[0], fidCoordsSingle[1], fidCoordsSingle[2])
					
					if not nodePresent:
						n = fidNodeACPC.AddControlPointWorld(vtk.vtkVector3d(fidCoordsSingle[0], fidCoordsSingle[1], fidCoordsSingle[2]))
						fidNodeACPC.SetNthControlPointLabel(n, iacpc)
						fidNodeACPC.SetNthControlPointLocked(n, True)

					fidCoordsACPC=getPointCoords('acpc', iacpc)

					fidNode = getMarkupsNode(iacpc)
					fidNode.GetDisplayNode().SetVisibility(0)
			else:
				nodePresent=False
				for ifid in range(fidNodeACPC.GetNumberOfControlPoints()):
					if iacpc in fidNodeACPC.GetNthControlPointLabel(ifid):
						nodePresent=True
				if not nodePresent and iacpc == 'mcp':
					n = fidNodeACPC.AddControlPointWorld(vtk.vtkVector3d(rasCoordMCP[0], rasCoordMCP[1], rasCoordMCP[2]))
					fidNodeACPC.SetNthControlPointLabel(n, iacpc)
					fidNodeACPC.SetNthControlPointLocked(n, True)

				if len(slicer.util.getNodes(f'{iacpc}')) > 0:
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(iacpc))

		fidCoordsMCP=getPointCoords('acpc', 'mcp')
		if not np.array_equal(adjustPrecision(rasCoordMCP), adjustPrecision(fidCoordsMCP)):
			for ifid in range(fidNodeACPC.GetNumberOfControlPoints()):
				if 'mcp' in fidNodeACPC.GetNthControlPointLabel(ifid):
					fidNodeACPC.SetNthControlPointPositionWorld(ifid, rasCoordMCP[0], rasCoordMCP[1], rasCoordMCP[2])

		fidNodeACPC.GetDisplayNode().SetVisibility(1)

		if 'midline' not in slicer.util.getNodes():
			fidNodeMidline = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
			if slicer.util.getNode('mid1').GetTransformNodeID() is not None:
				fidNodeMidline.SetAndObserveTransformNodeID(slicer.util.getNode('mid1').GetTransformNodeID())
			fidNodeMidline.SetName('midline')
			fidNodeMidline.AddDefaultStorageNode()
			fidNodeMidline.GetStorageNode().SetCoordinateSystem(coordSys)
		else:
			fidNodeMidline = getMarkupsNode('midline')

		midline_coords=[]
		for imid in ('mid1', 'mid2', 'mid3', 'mid4', 'mid5'):
			fidNodeMid = getMarkupsNode(imid)
			if fidNodeMid is not None:
				fidCoordsSingle=getPointCoords(imid, imid)
				fidCoordsMid=getPointCoords('midline', imid)

				if not np.array_equal(adjustPrecision(fidCoordsSingle), adjustPrecision(np.zeros(3))):
					if not np.array_equal(adjustPrecision(fidCoordsSingle), adjustPrecision(fidCoordsMid)):
						nodePresent=False
						for ifid in range(fidNodeMidline.GetNumberOfControlPoints()):
							if imid in fidNodeMidline.GetNthControlPointLabel(ifid):
								nodePresent=True
								fidNodeMidline.SetNthControlPointPositionWorld(ifid, fidCoordsSingle[0], fidCoordsSingle[1], fidCoordsSingle[2])
						
						if not nodePresent:
							n = fidNodeMidline.AddControlPointWorld(vtk.vtkVector3d(fidCoordsSingle[0], fidCoordsSingle[1], fidCoordsSingle[2]))
							fidNodeMidline.SetNthControlPointLabel(n, imid)
							fidNodeMidline.SetNthControlPointLocked(n, True)

						fidCoordsMid=getPointCoords('midline', imid)

						
						fidNodeMid.GetDisplayNode().SetVisibility(0)

				elif not np.array_equal(adjustPrecision(fidCoordsMid), adjustPrecision(np.zeros(3))):
					if len(slicer.util.getNodes(f'{imid}')) > 0:
						slicer.mrmlScene.RemoveNode(slicer.util.getNode(imid))

				midline_coords.append((imid,fidCoordsMid))

		fidNodeMidline.GetDisplayNode().SetVisibility(1)

		layoutManager = slicer.app.layoutManager()
		volNode=slicer.util.getNode(layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode().GetBackgroundVolumeID())

		if not os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_coordsystem.json")):
			coordsystem_file_json = {}
			coordsystem_file_json['IntendedFor'] = os.path.join(self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
			coordsystem_file_json['FiducialsCoordinateSystem'] = 'RAS'
			coordsystem_file_json['FiducialsCoordinateUnits'] = 'mm'
			coordsystem_file_json['FiducialsCoordinateSystemDescription'] = "RAS orientation: Origin halfway between LPA and RPA, positive x-axis towards RPA, positive y-axis orthogonal to x-axis through Nasion,  z-axis orthogonal to xy-plane, pointing in superior direction."
			coordsystem_file_json['FiducialsCoordinates'] = {}
		else:
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_coordsystem.json")) as coordsystem_file:
				coordsystem_file_json = json.load(coordsystem_file)
		
		coordsystem_file_json['IntendedFor'] = os.path.join(self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1],volNode.GetName())
		coordsystem_file_json['FiducialsCoordinates']['ac']=adjustPrecision(rasCoordAC).tolist()
		coordsystem_file_json['FiducialsCoordinates']['pc']=adjustPrecision(rasCoordPC).tolist()
		coordsystem_file_json['FiducialsCoordinates']['mcp']=adjustPrecision(rasCoordMCP).tolist()

		for imid in midline_coords:
			coordsystem_file_json['FiducialsCoordinates'][imid[0]]=adjustPrecision(imid[1]).tolist()

		json_output = json.dumps(coordsystem_file_json, indent=4)
		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_coordsystem.json"), 'w') as fid:
			fid.write(json_output)
			fid.write('\n')

		

	def getFidCoords(self, fids):
		"""
		Gets the coordinates for fiducials.
		
		:param fids: fiducials to get coordinates for
		:type fids: array
		:return rasCoord: The coordinates
		"""
		for i in range(fids.GetNumberOfControlPoints()):
			rasCoord = np.zeros(3)
			fids.GetNthControlPointPositionWorld(i, rasCoord)
			rasCoord = rasCoord

		return rasCoord

	def onAcpcTransformDeleteButton(self):
		if self.ui.acpcTransformCBox.currentNode() is not None:
			qm = qt.QMessageBox()
			ret = qm.question(self, '', 'Are you sure you want to delete the ACPC transform?', qm.Yes | qm.No)

			if ret == qm.Yes:
				slicer.mrmlScene.RemoveNode(self.ui.acpcTransformCBox.currentNode())
				os.remove(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'acpc_transform.h5'))
				inputTransform = slicer.mrmlScene.GetFirstNodeByName('from-acpcTransform_to-localizer_transform')
				if inputTransform is not None:
					slicer.mrmlScene.RemoveNode(inputTransform)
					os.remove(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame', 'from-acpcTransform_to-localizer_transform.h5'))
				fids = slicer.util.getNode('midline')
				for ifid in range(fids.GetNumberOfControlPoints()):
					rasCoord = np.zeros(3)
					fids.GetNthControlPointPositionWorld(ifid, rasCoord)
					if 'mid1' in fids.GetNthControlPointLabel(ifid):
						self.ui.mid1X.value = rasCoord[0]
						self.ui.mid1Y.value = rasCoord[1]
						self.ui.mid1Z.value = rasCoord[2]
					elif 'mid2' in fids.GetNthControlPointLabel(ifid):
						self.ui.mid2X.value = rasCoord[0]
						self.ui.mid2Y.value = rasCoord[1]
						self.ui.mid2Z.value = rasCoord[2]
					elif 'mid3' in fids.GetNthControlPointLabel(ifid):
						self.ui.mid3X.value = rasCoord[0]
						self.ui.mid3Y.value = rasCoord[1]
						self.ui.mid3Z.value = rasCoord[2]
					elif 'mid4' in fids.GetNthControlPointLabel(ifid):
						self.ui.mid4X.value = rasCoord[0]
						self.ui.mid4Y.value = rasCoord[1]
						self.ui.mid4Z.value = rasCoord[2]
					elif 'mid5' in fids.GetNthControlPointLabel(ifid):
						self.ui.mid5X.value = rasCoord[0]
						self.ui.mid5Y.value = rasCoord[1]
						self.ui.mid5Z.value = rasCoord[2]

				fids = slicer.util.getNode('acpc')
				for ifid in range(fids.GetNumberOfControlPoints()):
					rasCoord = np.zeros(3)
					fids.GetNthControlPointPositionWorld(ifid, rasCoord)
					if 'ac' in fids.GetNthControlPointLabel(ifid):
						self.ui.acX.value = rasCoord[0]
						self.ui.acY.value = rasCoord[1]
						self.ui.acZ.value = rasCoord[2]
					elif 'pc' in fids.GetNthControlPointLabel(ifid):
						self.ui.pcX.value = rasCoord[0]
						self.ui.pcY.value = rasCoord[1]
						self.ui.pcZ.value = rasCoord[2]
					elif 'mcp' in fids.GetNthControlPointLabel(ifid):
						self.ui.mcpX.value = rasCoord[0]
						self.ui.mcpY.value = rasCoord[1]
						self.ui.mcpZ.value = rasCoord[2]

	def onAcpcTransformButton(self):
		"""
		Slot for ``Run ACPC Transform`` button
		"""
		outputTransform = slicer.vtkMRMLLinearTransformNode()
		outputTransform.SetName('acpc_transform')
		outputTransform.SetAttribute('acpc', '1')
		slicer.mrmlScene.AddNode(outputTransform)

		acpc_line = planMarkupsNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsLineNode')
		acpc_line.SetName('acpc_line')
		acpc_line.AddDefaultStorageNode()
		acpc_line.GetStorageNode().SetCoordinateSystem(coordSys)

		midlineNode = slicer.util.getNode('midline')
		
		pcCoords = getPointCoords('pc', 'pc')
		if np.array_equal(adjustPrecision(pcCoords), adjustPrecision(np.array([0.0] * 3))):
			pcCoords = getPointCoords('acpc', 'pc')

		acCoords = getPointCoords('ac', 'ac')
		if np.array_equal(adjustPrecision(acCoords), adjustPrecision(np.array([0.0] * 3))):
			acCoords = getPointCoords('acpc', 'ac')

		n = acpc_line.AddControlPointWorld(vtk.vtkVector3d(acCoords[0], acCoords[1], acCoords[2]))
		acpc_line.SetNthControlPointLabel(n, 'ac')
		acpc_line.SetNthControlPointLocked(n, 1)

		n = midlineNode.AddControlPointWorld(vtk.vtkVector3d(acCoords[0], acCoords[1], acCoords[2]))
		midlineNode.SetNthControlPointLabel(n, 'ac')
		midlineNode.SetNthControlPointLocked(n, True)
		
		n = acpc_line.AddControlPointWorld(vtk.vtkVector3d(pcCoords[0], pcCoords[1], pcCoords[2]))
		acpc_line.SetNthControlPointLabel(n, 'pc')
		acpc_line.SetNthControlPointLocked(n, 1)

		n = midlineNode.AddControlPointWorld(vtk.vtkVector3d(pcCoords[0], pcCoords[1], pcCoords[2]))
		midlineNode.SetNthControlPointLabel(n, 'pc')
		midlineNode.SetNthControlPointLocked(n, True)
		
		params = {'ACPC':acpc_line, 'Midline':midlineNode,  'OutputTransform':outputTransform}
		slicer.cli.runSync((slicer.modules.acpctransform), None, params, update_display=True)
		slicer.util.saveNode(outputTransform, os.path.join(self._parameterNode.GetParameter('derivFolder'), 'acpc_transform.h5'))
		
		self.ui.acpcTransformCBox.setCurrentNode(outputTransform)
		slicer.mrmlScene.RemoveNode(acpc_line)
		
		for ifid in range(midlineNode.GetNumberOfControlPoints()):
			if 'ac' in midlineNode.GetNthControlPointLabel(ifid):
				midlineNode.RemoveNthControlPoint(ifid)

		for ifid in range(midlineNode.GetNumberOfControlPoints()):
			if 'pc' in midlineNode.GetNthControlPointLabel(ifid):
				midlineNode.RemoveNthControlPoint(ifid)

	def runFrameAlignment(self):
		inputTransform = slicer.vtkMRMLLinearTransformNode()
		inputTransform.SetName('from-acpcTransform_to-localizer_transform')
		slicer.mrmlScene.AddNode(inputTransform)
		transformNodeCTSpace = slicer.mrmlScene.GetNodesByName('*desc-affine_from-ctFrame_to*')
		if inputTransform is not None and transformNodeCTSpace is not None:
			models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			for imodel in models:
				if 'model_desc-frame_label-all_pole' in imodel.GetName():
					slicer.mrmlScene.RemoveNode(imodel)

			inputFiducials = slicer.mrmlScene.GetFirstNodeByName('frame_top_bottom')
			fidNode = slicer.mrmlScene.GetFirstNodeByName('frame_fids')
			inputModel = slicer.util.loadModel(os.path.join(self._parameterNode.GetParameter('script_path'), 'resources', 'models', 'model_desc-frame_label-all_pole.vtk'))
			inputModel.SetName('model_desc-frame_label-all_pole')
			fidNode.SetAndObserveTransformNodeID(inputTransform.GetID())
			inputFiducials.SetAndObserveTransformNodeID(inputTransform.GetID())
			transformType = 0
			numIterations = 100
			vtkNode = runFrameModelRegistration(inputFiducials, inputModel, inputTransform, transformType, numIterations)
			slicer.util.saveNode(inputModel, os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame', 'model_desc-frame_label-all_pole.vtk'))
			slicer.util.saveNode(inputTransform, os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame', 'from-acpcTransform_to-localizer_transform.h5'))
			inputTransform.RemoveNodeReferenceIDs(slicer.vtkMRMLTransformNode.GetMovingNodeReferenceRole())
			inputTransform.RemoveNodeReferenceIDs(slicer.vtkMRMLTransformNode.GetFixedNodeReferenceRole())
		return inputTransform

	def onACPCTransformCBox(self):
		"""
		Slot for ``Select Transform:`` combo box
		"""
		if self.ui.acpcTransformCBox.currentNode() is not None and self.active:
			self.ACPCTransform = slicer.mrmlScene.GetFirstNodeByName('acpc_transform')
			inputTransform = slicer.mrmlScene.GetFirstNodeByName('from-fiducials_to-localizer_transform')

			transformNodeCT = None
			if len(slicer.util.getNodes('*from-ctFrame_to*')) > 0:
				transformNodeCT = list(slicer.util.getNodes('*from-ctFrame_to*').values())[0]
			
			fids = slicer.util.getNode('midline')
			for ifid in range(fids.GetNumberOfControlPoints()):
				rasCoord = np.zeros(3)
				fids.GetNthControlPointPositionWorld(ifid, rasCoord)
				if 'mid1' in fids.GetNthControlPointLabel(ifid):
					self.ui.mid1X.value = rasCoord[0]
					self.ui.mid1Y.value = rasCoord[1]
					self.ui.mid1Z.value = rasCoord[2]
				elif 'mid2' in fids.GetNthControlPointLabel(ifid):
					self.ui.mid2X.value = rasCoord[0]
					self.ui.mid2Y.value = rasCoord[1]
					self.ui.mid2Z.value = rasCoord[2]
				elif 'mid3' in fids.GetNthControlPointLabel(ifid):
					self.ui.mid3X.value = rasCoord[0]
					self.ui.mid3Y.value = rasCoord[1]
					self.ui.mid3Z.value = rasCoord[2]
				elif 'mid4' in fids.GetNthControlPointLabel(ifid):
					self.ui.mid4X.value = rasCoord[0]
					self.ui.mid4Y.value = rasCoord[1]
					self.ui.mid4Z.value = rasCoord[2]
				elif 'mid5' in fids.GetNthControlPointLabel(ifid):
					self.ui.mid5X.value = rasCoord[0]
					self.ui.mid5Y.value = rasCoord[1]
					self.ui.mid5Z.value = rasCoord[2]

			fids = slicer.util.getNode('acpc')
			for ifid in range(fids.GetNumberOfControlPoints()):
				rasCoord = np.zeros(3)
				fids.GetNthControlPointPositionWorld(ifid, rasCoord)
				if 'ac' in fids.GetNthControlPointLabel(ifid):
					self.ui.acX.value = rasCoord[0]
					self.ui.acY.value = rasCoord[1]
					self.ui.acZ.value = rasCoord[2]
				elif 'pc' in fids.GetNthControlPointLabel(ifid):
					self.ui.pcX.value = rasCoord[0]
					self.ui.pcY.value = rasCoord[1]
					self.ui.pcZ.value = rasCoord[2]
				elif 'mcp' in fids.GetNthControlPointLabel(ifid):
					self.ui.mcpX.value = rasCoord[0]
					self.ui.mcpY.value = rasCoord[1]
					self.ui.mcpZ.value = rasCoord[2]

			layoutManager = slicer.app.layoutManager()
			volumeNode = slicer.util.getNode(layoutManager.sliceWidget('Red').sliceLogic().GetSliceCompositeNode().GetBackgroundVolumeID())
			slicer.util.setSliceViewerLayers(background=volumeNode)
			#applicationLogic = slicer.app.applicationLogic()
			#applicationLogic.FitSliceToAll()
			slicer.util.resetSliceViews()

#
# anatomicalLandmarksLogic
#

class anatomicalLandmarksLogic(ScriptedLoadableModuleLogic):
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
		self.anatomicalLandmarksInstance = None
		self.FrameAutoDetect = False

	def getParameterNode(self, replace=False):
		"""Get the anatomicalLandmarks parameter node.

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
		""" Create the anatomicalLandmarks parameter node.

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
# anatomicalLandmarksTest
#

class anatomicalLandmarksTest(ScriptedLoadableModuleTest):
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
		self.test_anatomicalLandmarks1()

	def test_anatomicalLandmarks1(self):
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
		inputVolume = SampleData.downloadSample('anatomicalLandmarks1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = anatomicalLandmarksLogic()

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
