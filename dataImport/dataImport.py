import os
import sys
import shutil
import pandas as pd
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

from helpers.helpers import vtkModelBuilderClass,getFrameCenter, getReverseTransform, addCustomLayouts, hex2rgb
from helpers.variables import coordSys, slicerLayout, surgical_info_dict

#
# dataImport
#

class dataImport(ScriptedLoadableModule):
	"""Uses ScriptedLoadableModule base class, available at:
	https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
	"""

	def __init__(self, parent):
		ScriptedLoadableModule.__init__(self, parent)
		self.parent.title = "01: Data Import"
		self.parent.categories = ["trajectoryGuide"]
		self.parent.dependencies = []
		self.parent.contributors = ["Greydon Gilmore (Western University)"]
		self.parent.helpText = """
This module loads a patient data directory for trajectoryGuide.\n
For use details see <a href="https://trajectoryguide.greydongilmore.com/widgets/01_patient_directory.html">module documentation</a>.
"""
		self.parent.acknowledgementText = ""


#
# dataImportWidget
#

class dataImportWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
		self.usePreviousValues = True
		self.RenameScans = True
		self.previousValues = {}
		self.patient_data_directory = []

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
		self.logic = dataImportLogic()
		
		# Connections
		self._setupConnections()
		
	def _loadUI(self):
		# Load widget from .ui file (created by Qt Designer)
		self.uiWidget = slicer.util.loadUI(self.resourcePath('UI/dataImport.ui'))
		self.layout.addWidget(self.uiWidget)
		self.ui = slicer.util.childWidgetVariables(self.uiWidget)
		self.uiWidget.setMRMLScene(slicer.mrmlScene)
		
	def _setupConnections(self):
		# These connections ensure that we update parameter node when scene is closed
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
		self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
		
		# These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
		# (in the selected parameter node).
		
		self.ui.directoryButton.connect('clicked(bool)', self.setExistingDirectory)
		self.ui.renameScansButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onRenameScansButtonGroupClicked)
		self.ui.usePreviousValuesButtonGroup.connect('buttonClicked(QAbstractButton*)', self.onUsePreviousValuesClicked)
		self.ui.DefaultDirectoryButton.connect('clicked(bool)', self.onDefaultDirectoryButton)
		self.ui.LoadScansButton.connect('clicked(bool)', self.onLoadScansButton)
		
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

	def onLoadScansButton(self):

		self.logic.importData(self.patient_data_directory, self.usePreviousValues, self.RenameScans)

	def setExistingDirectory(self):
		with open(self._parameterNode.GetParameter('trajectoryGuide_settings'), 'r') as (settings_file):
			trajectoryGuide_settings = json.load(settings_file)
		if os.path.exists(os.path.normpath(trajectoryGuide_settings['default_dir'])):
			default_dir = os.path.normpath(trajectoryGuide_settings['default_dir'])
		else:
			default_dir = os.path.expanduser('HOME')
		
		parent = None
		for w in slicer.app.topLevelWidgets():
			if hasattr(w,'objectName'):
				if w.objectName == 'qSlicerMainWindow':
					parent=w

		self.patient_data_directory = os.path.normpath(qt.QFileDialog().getExistingDirectory(parent, 'Open a folder', default_dir, qt.QFileDialog.ShowDirsOnly))
		if self.patient_data_directory:
			self.ui.directoryLabel.setText(self.patient_data_directory)

	def onDefaultDirectoryButton(self):
		parent = None
		for w in slicer.app.topLevelWidgets():
			if hasattr(w,'objectName'):
				if w.objectName == 'qSlicerMainWindow':
					parent=w

		data_directory = qt.QFileDialog().getExistingDirectory(parent, 'Open a folder', os.path.expanduser('HOME'), qt.QFileDialog.ShowDirsOnly)
		with open(self._parameterNode.GetParameter('trajectoryGuide_settings'), 'r') as (settings_file):
			trajectoryGuide_settings = json.load(settings_file)
		trajectoryGuide_settings['default_dir'] = os.path.normpath(data_directory)
		file = self._parameterNode.GetParameter('trajectoryGuide_settings')
		json_output = json.dumps(trajectoryGuide_settings, indent=4)
		with open(file, 'w') as (fid):
			fid.write(json_output)
			fid.write('\n')

	def onRenameScansButtonGroupClicked(self, button):
		"""
		**Slot for** ``Rename Scans`` **button.**

		:param button: The number that refers to the button that's clicked
		:type button: Macro - Integer
		
		"""
		if 'yes' in button.text.lower():
			self.RenameScans = True
		elif 'no' in button.text.lower():
			self.RenameScans = False

	def onUsePreviousValuesClicked(self, button):
		"""
		**Slot for** ``Use Previous Values`` **button.**

		:param button: The number that refers to the button that's clicked
		:type button: Macro - Integer
		
		"""
		if 'yes' in button.text.lower():
			self.usePreviousValues = True
		elif 'no' in button.text.lower():
			self.usePreviousValues = False


#
# dataImportLogic
#

class dataImportLogic(ScriptedLoadableModuleLogic):
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
		self.dataImportInstance = None
		self.FrameAutoDetect = False

	def getParameterNode(self, replace=False):
		"""Get the dataImport parameter node.

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
		""" Create the dataImport parameter node.

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

	def importData(self, patient_data_directory, usePreviousValues, RenameScans):
		""" Slot for when the "Load Scans" button is clicked.

		"""
		
		#slicer.mrmlScene.Clear()
		self._parameterNode = self.getParameterNode()

		self.bidsFolder = patient_data_directory
		self.derivFolder = os.path.join(os.path.dirname(os.path.dirname(self.bidsFolder)),'derivatives', os.path.basename(self.bidsFolder))
		
		self._parameterNode.SetParameter("bidsFolder", self.bidsFolder)
		self._parameterNode.SetParameter('derivFolder', self.derivFolder)

		self.setPatientSpecificParamters(self._parameterNode)

		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'),'settings', 'model_visibility.json')) as settings_file:
			slice_vis = json.load(settings_file)

		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'),'settings', 'model_color.json')) as settings_file:
			modelColors = json.load(settings_file)

		if not os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")):
			surgical_info_json = {}
			surgical_info_json['subject'] = os.path.basename(self._parameterNode.GetParameter('derivFolder'))
			surgical_info_json['surgery_date'] = []
			surgical_info_json['surgeon'] = []
			surgical_info_json['target'] = []
			surgical_info_json['frame_system'] = []
			surgical_info_json['trajectories'] = {}
			
			json_output = json.dumps(surgical_info_dict(surgical_info_json), indent=4)
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json"),'w') as fid:
				fid.write(json_output)
				fid.write('\n')
		
		csvfile = os.path.join(self._parameterNode.GetParameter('derivFolder'), 'summaries', 'contact_summary.csv')
		if all([os.path.exists(csvfile), usePreviousValues==False]):
			os.remove(csvfile)

		#### Load Transforms
		if not os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'source')):
			os.makedirs(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'source'))

		self.acpcTransform = None
		self.frameTransform = None
		self.localizerTransform = None
		surgical_data = None
		for root, directories, filenames in os.walk(self._parameterNode.GetParameter('derivFolder')):
			for filename in filenames:
				if any(filename.endswith(y) for y in {'.txt','.tfm','.h5'}):
					full_filename = os.path.join(root, filename)
					if 'acpc_transform' in filename:
						self.acpcTransform = slicer.util.loadTransform(full_filename)
					if 'Frame_to-' in filename and 'desc-rigid' in filename:
						frameTransform = slicer.util.loadTransform(full_filename)

						self.frameTransform = getReverseTransform(frameTransform, True)

		#### Load all files within subject 'frame' directory
		frameReg = False
		frameOrigVol = None
		frameNode = None
		self.frameTransform = None
		for ifile in [x for x in glob.glob(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame', '*')) if not os.path.isdir(x)]:
			if any(ifile.endswith(y) for y in {'.txt','.tfm','.h5'}):
				if 'from-fiducials_to-localizer_xfm' in ifile:
					self.frameTransform = slicer.util.loadTransform(ifile)
					#self.frameTransform=self.getReverseTransform(frameTransform, True)

			elif any(ifile.endswith(x) for x in {'.nii','.nii.gz'}):
				frameNode = slicer.util.loadVolume(ifile)
				with open(ifile.split('.nii')[0] + '.json') as fid:
					file_attrbs = json.load(fid)

				if file_attrbs['coregistered']:
					frameNode.SetAttribute('coreg', '1')
					frameNode.SetAttribute('regVol', '0')
				else:
					frameNode.SetAttribute('coreg', '0')
					frameNode.SetAttribute('regVol', '1')

				if file_attrbs['vol_type']=='frame':
					frameNode.SetAttribute('frameVol', '1')

				frameOrigVol = file_attrbs['source_name']
				frameReg=True

			elif all([ifile.endswith('fiducials_fids.fcsv'), usePreviousValues]):
				#frameFidsNode = slicer.util.loadMarkups(ifile)
				#frameFidsNode.GetDisplayNode().SetVisibility(0)

				fidsDataframe = self.fcsvLPStoRAS(ifile)

				fidNodeFrame=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
				fidNodeFrame.SetName(os.path.basename(ifile).split('.fcsv')[0])
				fidNodeFrame.AddDefaultStorageNode()
				fidNodeFrame.GetStorageNode().SetCoordinateSystem(1)
				fidNodeFrame.GetDisplayNode().SetGlyphScale(0.8)
				fidNodeFrame.GetDisplayNode().SetTextScale(1.0)
				fidNodeFrame.GetDisplayNode().SetSelectedColor(1, 0, 0)
				wasModify=fidNodeFrame.StartModify()
				for index, ipoint in fidsDataframe.iterrows():
					n = fidNodeFrame.AddControlPoint(vtk.vtkVector3d(ipoint['x'], ipoint['y'], ipoint['z']))
					fidNodeFrame.SetNthControlPointLabel(n, ipoint['label'])

				fidNodeFrame.EndModify(wasModify)
				fidNodeFrame.GetDisplayNode().SetVisibility(0)

				combined_frame=[x for x in glob.glob(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'frame','*_localizer.vtk')) if 'label-all_localizer' in os.path.basename(x)]
				
				if combined_frame:
					node = slicer.util.loadModel(combined_frame[0])
					node.GetModelDisplayNode().SetColor(1,0,0)
					node.GetDisplayNode().VisibilityOff()
					node.GetStorageNode().SetCoordinateSystem(coordSys)

			#### Frame FIDs
			elif all([ifile.endswith('topbottom_fids.fcsv'), usePreviousValues]):
				frame_top_bottom = slicer.util.loadMarkups(ifile)
				frame_top_bottom.GetDisplayNode().SetVisibility(0)

			#### Frame localizer
			elif all([ifile.endswith('.vtk'), usePreviousValues]):
				frameModelNode = node = slicer.util.loadModel(ifile)
				frameModelNode.GetDisplayNode().SetVisibility(0)
				frameModelNode.GetDisplayNode().SetVisibility2D(0)
				frameModelNode.GetDisplayNode().SetRepresentation(2)
				frameModelNode.GetDisplayNode().LightingOff()

		# check if first time loading nifti files
		for inifti in [x for x in glob.glob(os.path.join(self.bidsFolder, '**/*'),recursive=True) if x.endswith((".nii",".gz"))]:
			if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), 'source', os.path.basename(inifti))):
				files = [x for x in os.listdir(os.path.join(self._parameterNode.GetParameter('derivFolder'))) if any(x.endswith(y) for y in {'.nii', '.nii.gz'})]
				file_sourcenames=[]
				for f in files:
					if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + '.json')):
						with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f.split('.nii')[0] + '.json')) as (file):
							file_sidecar_temp = json.load(file)
						file_sourcenames.append(file_sidecar_temp['source_name'])

				if os.path.basename(inifti) not in file_sourcenames:
					if frameOrigVol is not None:
						if os.path.basename(inifti) != frameOrigVol:
							shutil.copy2(inifti, os.path.join(self._parameterNode.GetParameter('derivFolder'), os.path.basename(inifti)))
					else:
						shutil.copy2(inifti, os.path.join(self._parameterNode.GetParameter('derivFolder'), os.path.basename(inifti)))
			else:
				if frameOrigVol is not None:
					if os.path.basename(inifti) != frameOrigVol:
						shutil.copy2(inifti, os.path.join(self._parameterNode.GetParameter('derivFolder'), 'source', os.path.basename(inifti)))
						shutil.copy2(inifti, os.path.join(self._parameterNode.GetParameter('derivFolder'), os.path.basename(inifti)))
				else:
					shutil.copy2(inifti, os.path.join(self._parameterNode.GetParameter('derivFolder'), 'source', os.path.basename(inifti)))
					shutil.copy2(inifti, os.path.join(self._parameterNode.GetParameter('derivFolder'), os.path.basename(inifti)))

		#### Load all files within subject root derivative directory
		for ifile in [x for x in glob.glob(os.path.join(self._parameterNode.GetParameter('derivFolder'), '*')) if not os.path.isdir(x)]:
			if any(ifile.endswith(x) for x in {'.nii','.nii.gz'}):

				# Will only rename if in BIDS format
				if all(['ses-' in os.path.basename(ifile), RenameScans]):
					filen_parts=[]
					if 'sub-' in os.path.basename(ifile):
						filen_parts.append([x for x in os.path.basename(ifile).split('_') if 'sub' in x])
					if 'space-' in os.path.basename(ifile):
						filen_parts.append([x for x in os.path.basename(ifile).split('_') if 'space' in x])
					if 'acq-' in os.path.basename(ifile):
						filen_parts.append([x for x in os.path.basename(ifile).split('_') if 'acq' in x])

					filen_parts.append([x for x in os.path.basename(ifile).split('_') if 'nii' in x])
					fnew = "_".join([item for sublist in filen_parts for item in sublist])

					if not os.path.exists(os.path.join(os.path.dirname(ifile), fnew)):
						os.rename(ifile, os.path.join(os.path.dirname(ifile), fnew))

					node = slicer.util.loadVolume(os.path.join(os.path.dirname(ifile), fnew))
					final_filename = fnew
				else:    
					node = slicer.util.loadVolume(ifile)
					final_filename = os.path.basename(ifile)

				file_attrbs = {}
				json_file_orig=None
				write_json=False
				# if volume json settings file exists, load it and remove it
				if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), os.path.basename(ifile).split('.nii')[0] + '.json')):
					with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), os.path.basename(ifile).split('.nii')[0] + '.json')) as fid:
						file_attrbs = json.load(fid)

					json_file_orig = file_attrbs.copy()
				else:
					write_json=True
					file_attrbs['source_name'] = os.path.basename(ifile)
					file_attrbs['file_name'] = final_filename
					file_attrbs['node_name'] = node.GetName()
					file_attrbs['vol_type'] = ''
					file_attrbs['reference'] =''

				if frameNode is not None:
					if file_attrbs['source_name'] == frameOrigVol:
						slicer.mrmlScene.RemoveNode(node)
						continue

				file_attrbs['file_name'] = final_filename if file_attrbs['file_name'] != final_filename else file_attrbs['file_name']
				file_attrbs['node_name'] = node.GetName() if file_attrbs['node_name'] != node.GetName() else file_attrbs['node_name']

				node.GetDisplayNode().AutoWindowLevelOff()
				if 'window' in list(file_attrbs):
					node.GetDisplayNode().SetWindow(file_attrbs['window'])
				else:
					file_attrbs['window'] = node.GetDisplayNode().GetWindow()

				if 'level' in list(file_attrbs):
					node.GetDisplayNode().SetLevel(file_attrbs['level'])
				else:
					file_attrbs['level'] = node.GetDisplayNode().GetLevel()
				
				node.SetAttribute('regVol', '1')
				if 'coregistered' in list(file_attrbs):
					if file_attrbs['coregistered']:
						node.SetAttribute('coreg', '1')
					else:
						node.SetAttribute('coreg', '0')
				else:
					if 'space-' in node.GetName():
						file_attrbs['coregistered'] = True
						node.SetAttribute('coreg', '1')
					else:
						file_attrbs['coregistered'] = False
						node.SetAttribute('coreg', '0')

				node.SetAttribute('refVol', '0')
				if 'vol_type' in list(file_attrbs):
					if file_attrbs['vol_type']=='frame':
						node.SetAttribute('frameVol', '1')
					if file_attrbs['vol_type']=='reference':
						node.SetAttribute('refVol', '1')

				if json_file_orig is not None:
					new_items = {k: file_attrbs[k] for k in file_attrbs if k in json_file_orig and file_attrbs[k] != json_file_orig[k]}
					if len(new_items) > 0:
						write_json=True

				if write_json:
					json_file_temp = os.path.join(self._parameterNode.GetParameter('derivFolder'), final_filename.split('.nii')[0] + '.json')
					json_output = json.dumps(file_attrbs, indent=4)
					with open(json_file_temp, 'w') as fid:
						fid.write(json_output)
						fid.write('\n')
			
			#### Fiducial nodes
			elif all([ifile.endswith('coordsystem.json'), 'ses-' not in os.path.basename(ifile),usePreviousValues]):
				with open(ifile) as fid:
					coordsystem_file_json = json.load(fid)

				acpcNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
				acpcNode.SetName('acpc')
				acpcNode.AddDefaultStorageNode()
				acpcNode.GetStorageNode().SetCoordinateSystem(coordSys)
				acpcNode.GetDisplayNode().SetVisibility(1)

				midlineNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
				midlineNode.SetName('midline')
				midlineNode.AddDefaultStorageNode()
				midlineNode.GetStorageNode().SetCoordinateSystem(coordSys)
				midlineNode.GetDisplayNode().SetVisibility(0)

				for ifid in list(coordsystem_file_json['FiducialsCoordinates']):
					pointCoordsWorld=coordsystem_file_json['FiducialsCoordinates'][ifid]
					if ifid in ('ac','pc','mcp'):
						n = acpcNode.AddControlPointWorld(vtk.vtkVector3d(pointCoordsWorld[0], pointCoordsWorld[1], pointCoordsWorld[2]))
						acpcNode.SetNthControlPointLabel(n, ifid)
						acpcNode.SetNthControlPointLocked(n, True)

					elif ifid.startswith('mid'):
						n = midlineNode.AddControlPointWorld(vtk.vtkVector3d(pointCoordsWorld[0], pointCoordsWorld[1], pointCoordsWorld[2]))
						midlineNode.SetNthControlPointLabel(n, ifid)
						midlineNode.SetNthControlPointLocked(n, True)

			### Load model objects
			elif all([any(os.path.basename(ifile).endswith(x) for x in ('.vtk','.stl')), usePreviousValues]):

				planType=None
				objectType=None

				if 'ses-pre' in os.path.basename(ifile):
					planType='planned'
				elif 'ses-intra' in os.path.basename(ifile):
					planType='intra'
				elif 'ses-post' in os.path.basename(ifile):
					planType='actual'

				if '_lead' in os.path.basename(ifile):
					objectType='Lead'
				elif '_contact' in os.path.basename(ifile):
					objectType='Contact'
				elif '_track' in os.path.basename(ifile):
					objectType='Microelectrodes'
				elif '_activity' in os.path.basename(ifile):
					objectType='MERActivity'
				elif '_vta' in os.path.basename(ifile):
					objectType='VTA'

				if planType is not None and objectType is not None:
					if os.path.basename(ifile).endswith('.vtk'):
						vtkModelBuilder=vtkModelBuilderClass()
						vtkModelBuilder.filename=ifile
						vtkModelBuilder.model_color = modelColors[f'{planType}{objectType}Color']
						vtkModelBuilder.model_visibility = slice_vis[f'{planType}{objectType}3DVis']
						vtkModelBuilder.add_to_scene()
					elif os.path.basename(ifile).endswith('.stl'):
						node = slicer.util.loadModel(ifile)
						if isinstance(modelColors[f'{planType}{objectType}Color'],str):
							modelCol = hex2rgb(modelColors[f'{planType}{objectType}Color'])
						else:
							modelCol = modelColors[f'{planType}{objectType}Color']
						node.GetModelDisplayNode().SetColor(modelCol)
						node.GetModelDisplayNode().SetSelectedColor(modelCol)
						node.GetDisplayNode().SetSliceIntersectionThickness(1)
						node.GetModelDisplayNode().SetSliceIntersectionVisibility(1)

		#### Set model attribute for ProbeEye viewer
		models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
		for imodel in models:
			if '_lead' in imodel.GetName():
				imodel.SetAttribute('ProbeEye', '1')
			else:
				imodel.SetAttribute('ProbeEye', '0')

		with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_surgical_data.json")) as (surgical_file):
			surgical_data = json.load(surgical_file)

		if 'frame_system' in list(surgical_data):
			if surgical_data['frame_system']:
				self._parameterNode.SetParameter("frame_system", surgical_data['frame_system'])

		#### Load frame models if registration of frame has been performed
		if frameReg:
			arcToFrameTransform = slicer.vtkMRMLLinearTransformNode()
			arcToFrameTransform.SetName("arcToFrame")
			arcToFrameMatrix = vtk.vtkMatrix4x4()
			arcToFrameMatrix.SetElement( 0, 3, 100)
			arcToFrameMatrix.SetElement( 1, 3, 100)
			arcToFrameMatrix.SetElement( 2, 3, 100)
			arcToFrameTransform.SetMatrixTransformToParent(arcToFrameMatrix)
			slicer.mrmlScene.AddNode(arcToFrameTransform)

			node = slicer.util.loadModel(os.path.join(self._parameterNode.GetParameter('trajectoryGuidePath'), 'resources', 'models', 'arc_collar.vtk'))
			node.GetDisplayNode().SetVisibility(0)
			node.SetAndObserveTransformNodeID(arcToFrameTransform.GetID())

		#### Apply transform to data if transform exists
		transform_data=[]
		if os.path.exists(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_transform_items.json")):
			with open(os.path.join(self._parameterNode.GetParameter('derivFolder'), f"{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_transform_items.json")) as (transform_file):
				transform_data = json.load(transform_file)

		if transform_data:
			for itransform,inodes in transform_data.items():
				#if self.frameTransform is not None:
				#	slicer.util.getNode(itransform).SetAndObserveTransformNodeID(self.frameTransform.GetID())
				for inode in inodes:
					if len(slicer.util.getNodes(f'*{inode}*')) > 0:
						node=slicer.util.getNode(inode)
						node.SetAndObserveTransformNodeID(slicer.util.getNode(itransform).GetID())

		#### Get frame center if frame fiducials have been detected
		if len(slicer.util.getNodes('*fiducial_fids*')) > 0 and len(slicer.util.getNodes('*topbottom_fids*')) > 0:
			if 'frame_system' in list(surgical_data):
				if surgical_data:
					getFrameCenter(surgical_data['frame_system'])

		#if self.frameTransform is not None:
			#fcsvNodeName = f"*{self._parameterNode.GetParameter('derivFolder').split(os.path.sep)[-1]}_*desc-%s_fids*"
			#searchNodes=[fcsvNodeName % ('fiducials'),fcsvNodeName % ('topbottom'),
			#	'*frame_center*','*acpc*','*midline*','*entry*','*target*','*frame_rotation*'
			#]
		#	searchNodes=['*frame_rotation*']
		#	for inode in searchNodes:
		#		if len(slicer.util.getNodes(inode))>0:
		#			list(slicer.util.getNodes(inode).values())[0].SetAndObserveTransformNodeID(self.frameTransform.GetID())

		#### Reset 3D view and 2D views
		applicationLogic = slicer.app.applicationLogic()
		applicationLogic.FitSliceToAll()

		layoutManager = slicer.app.layoutManager()
		threeDWidget = layoutManager.threeDWidget(0)
		threeDView = threeDWidget.threeDView()
		threeDView.resetFocalPoint()
		renderer = threeDView.renderWindow().GetRenderers().GetFirstRenderer()
		renderer.SetBackground(0, 0, 0)
		renderer.SetBackground2(0, 0, 0)
		threeDView.renderWindow().Render()

		orientations = {
			'Red':'Axial', 
			'Yellow':'Sagittal', 
			'Green':'Coronal'
		}

		layoutManager = slicer.app.layoutManager()
		for sliceViewName in layoutManager.sliceViewNames():
			layoutManager.sliceWidget(sliceViewName).mrmlSliceNode().SetOrientation(orientations[sliceViewName])

		slicer.util.resetSliceViews()

	def fcsvLPStoRAS(self, fcsv_fname):
		coord_sys=[]
		with open(fcsv_fname, 'r+') as fid:
			rdr = csv.DictReader(filter(lambda row: row[0]=='#', fid))
			row_cnt=0
			for row in rdr:
				if row_cnt==0:
					coord_sys.append(str(list(row.values())[0]).split('=')[-1].strip())
				row_cnt +=1
		
		df = pd.read_csv(fcsv_fname, skiprows=2)
		if any(x in coord_sys for x in {'LPS','1'}):
			df['x']=df['x']*-1
			df['y']=df['y']*-1
		
		return df



#
# dataImportTest
#

class dataImportTest(ScriptedLoadableModuleTest):
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
		self.test_dataImport1()

	def test_dataImport1(self):
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
		inputVolume = SampleData.downloadSample('dataImport1')
		self.delayDisplay('Loaded test data set')

		inputScalarRange = inputVolume.GetImageData().GetScalarRange()
		self.assertEqual(inputScalarRange[0], 0)
		self.assertEqual(inputScalarRange[1], 695)

		outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
		threshold = 100

		# Test the module logic

		logic = dataImportLogic()

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
