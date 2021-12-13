
import qt, ctk, slicer, vtk, numpy as np, pandas as pd,os, shutil, csv, json, sys, subprocess, platform, math, re
from .variables import electrodeModels, coordSys, slicerLayout, trajectoryGuideLayout, trajectoryGuideAxialLayout, slicerLayoutAxial,\
microelectrodeModels
from random import uniform

cwd = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(1, os.path.dirname(cwd))

from settingsPanel.settingsPanel import settingsPanelWidget

RASsys = False
if coordSys == 1:
	RASsys = True

frame_align=True
circleFrameFiducials=False

class warningBox(qt.QMessageBox):
	__doc__ = 'Class for wanring message box. \n\n\tThis class displays a wanring message box to the user. \n\n\tParameters\n\t----------\n\ttext: str\n\t\tText to appear in the error box.\n\t'

	def __init__(self, text):
		super(warningBox, self).__init__()
		self.setIcon(qt.QMessageBox.Critical)
		self.setWindowTitle('Error')
		self.setText(text)
		self.exec_()

pip_upgrade=False
try:
	import pandas
except:
	if not pip_upgrade:
		slicer.util.pip_install("pip --upgrade")
		pip_upgrade=True
	slicer.util.pip_install("pandas")

try:
	from skimage import morphology
	from skimage import measure
	from skimage.filters import threshold_otsu
except:
	if not pip_upgrade:
		slicer.util.pip_install("pip --upgrade")
		pip_upgrade=True
	slicer.util.pip_install("scikit-image")

try:
	import scipy
	from scipy import ndimage
	from scipy.spatial import ConvexHull, Delaunay
except:
	if not pip_upgrade:
		slicer.util.pip_install("pip --upgrade")
		pip_upgrade=True
	slicer.util.pip_install("scipy")

class CheckableComboBox(qt.QComboBox):
	def __init__(self):
		super(CheckableComboBox, self).__init__()
		self.view().pressed.connect(self.handleItemPressed)
		self.setModel(qt.QStandardItemModel(self))

	def handleItemPressed(self, index):
		item = self.model().itemFromIndex(index)
		if item.checkState() == qt.Qt.Checked:
			item.setCheckState(qt.Qt.Unchecked)
		else:
			item.setCheckState(qt.Qt.Checked)

	def item_checked(self, index):
		item = self.model().item(index, 0)
		return item.checkState() == qt.Qt.Checked

	def check_items(self):
		checkedItems = []
		for i in range(self.count):
			if self.item_checked(i):
				checkedItems.append(self.itemText(i))
		return checkedItems

class regComboBox(qt.QComboBox):
	def __init__(self):
		super(regComboBox, self).__init__()
		self.setModel(qt.QStandardItemModel(self))
	
class vtkModelBuilderClass:
	def __init__(self, coords=0, tube_radius=0, tube_thickness=0, filename=None, nodeName = None, 
		electrode=False, plane=0, electrodeLen=0, model_color=None, model_visibility=None):

		self.coords = coords
		self.tube_radius = tube_radius
		self.tube_thickness = tube_thickness
		self.filename = filename
		self.nodeName = nodeName
		self.electrode = electrode
		self.plane = plane
		self.electrodeLen = electrodeLen
		self.model_color = model_color
		self.model_visibility = model_visibility
		self.final_model=None

	def _compute_transform(self, start, end, rotate):
		normalized_x = np.zeros(3)
		normalized_y = np.zeros(3)
		normalized_z = np.zeros(3)
		vtk.vtkMath.Subtract(end, start, normalized_x)
		vtk.vtkMath.Normalize(normalized_x)
		rng = vtk.vtkMinimalStandardRandomSequence()
		rng.SetSeed(8775070)
		arbitrary = np.zeros(3)

		for i in range(0, 3):
			rng.Next()
			arbitrary[i] = rng.GetRangeValue(-10, 10)

		vtk.vtkMath.Cross(normalized_x, arbitrary, normalized_z)
		vtk.vtkMath.Normalize(normalized_z)
		vtk.vtkMath.Cross(normalized_z, normalized_x, normalized_y)

		matrix = vtk.vtkMatrix4x4()
		matrix.Identity()
		for i in range(3):
			matrix.SetElement(i, 0, normalized_x[i])
			matrix.SetElement(i, 1, normalized_y[i])
			matrix.SetElement(i, 2, normalized_z[i])

		transform = vtk.vtkTransform()
		transform.Translate(start)
		transform.Concatenate(matrix)

		if rotate:
			transform.RotateY(90.0)

		return transform

	def _transform_item(self, item, transform):
		transformed = vtk.vtkTransformPolyDataFilter()
		transformed.SetInputConnection(item.GetOutputPort())
		transformed.SetTransform(transform)
		transformed.Update()

		return transformed

	def _create_sphere(self,tube_radius):
		sphere = vtk.vtkSphereSource()
		sphere.SetThetaResolution(128)
		sphere.SetPhiResolution(128)
		sphere.SetRadius(tube_radius)
		plane = vtk.vtkPlane()
		plane.SetOrigin(0, 0, 0)
		plane.SetNormal(0, 0, -1.0)
		clipper = vtk.vtkClipPolyData()
		clipper.SetInputConnection(sphere.GetOutputPort())
		clipper.SetClipFunction(plane)
		clipper.SetValue(0)
		clipper.Update()

		return clipper

	def _create_pipe(self, height, radius, thickness):
		disk = vtk.vtkDiskSource()
		disk.SetCircumferentialResolution(128)
		disk.SetRadialResolution(1)
		disk.SetOuterRadius(radius)
		disk.SetInnerRadius(radius - thickness)
		pipe = vtk.vtkLinearExtrusionFilter()
		pipe.SetInputConnection(disk.GetOutputPort())
		pipe.SetExtrusionTypeToNormalExtrusion()
		pipe.SetVector(0, 0, 1)
		pipe.SetScaleFactor(height)
		pipe.Update()
		return pipe

	def _combine_polydata(self, source1, source2):
		if source2 is None:
			return source1
		elif source1 is None:
			return source2

		combo = vtk.vtkAppendPolyData()
		combo.AddInputData(source1.GetOutput())
		combo.AddInputData(source2.GetOutput())
		combo.Update()

		return self._clean_mesh(combo)

	def _clean_mesh(self, source):
		clean = vtk.vtkCleanPolyData()
		clean.SetInputData(source.GetOutput())
		clean.Update()
		return clean

	def build_electrode(self):
		NormVec = norm_vec(np.array(self.coords[0:3]).astype(float), np.array(self.coords[3:]).astype(float))
		start_point_pipe = np.array(np.array(self.coords[0:3]).astype(float) + NormVec * self.tube_radius)
		start_point_sphere = np.array(np.array(self.coords[0:3]).astype(float) + NormVec * self.tube_radius)
		end_point_pipe = np.array(self.coords[3:]).astype(float)
		end_point_sphere = np.array(self.coords[3:]).astype(float)
		transform = self._compute_transform(start_point_sphere, end_point_sphere, True)
		
		sphere = self._create_sphere(self.tube_radius)
		sphere = self._transform_item(sphere, transform)
		sphere.Update()
		
		length_pipe = np.linalg.norm(start_point_pipe - end_point_pipe)
		transform = self._compute_transform(start_point_pipe, end_point_pipe, True)
		
		pipe = self._create_pipe(length_pipe, self.tube_radius, self.tube_thickness)
		pipe = self._transform_item(pipe, transform)
		pipe.Update()
		
		self.final_model = self._combine_polydata(pipe, sphere)
		self._save_file()

	def build_line(self):
		start_point_pipe = np.array(self.coords[0:3]).astype(float)
		end_point_pipe = np.array(self.coords[3:]).astype(float)
		length_pipe = np.linalg.norm(start_point_pipe - end_point_pipe)
		transform = self._compute_transform(start_point_pipe, end_point_pipe, True)
		pipe = self._create_pipe(length_pipe, self.tube_radius, self.tube_thickness)
		self.final_model = self._transform_item(pipe, transform)
		self.final_model.Update()
		self._save_file()

	def build_cylinder(self):
		start_point_pipe = np.array(self.coords[0:3]).astype(float)
		end_point_pipe = np.array(self.coords[3:]).astype(float)
		length_pipe = np.linalg.norm(start_point_pipe - end_point_pipe)
		transform = self._compute_transform(start_point_pipe, end_point_pipe, False)
		transform.RotateZ(-90.0)
		transform.Scale(1.0, length_pipe, 1.0)
		transform.Translate(0, 0.5, 0)
		cylinderSource = vtk.vtkCylinderSource()
		cylinderSource.SetCenter(0.0, 0.0, 0.0)
		cylinderSource.SetRadius(self.tube_radius)
		cylinderSource.SetResolution(100)
		self.final_model = self._transform_item(cylinderSource, transform)
		self.final_model.Update()
		self._save_file()

	def build_dir_bottomContact(self):
		NormVec = norm_vec(np.array(self.coords[0:3]).astype(float), np.array(self.coords[3:]).astype(float))
		
		start_point_pipe = np.array(np.array(self.coords[0:3]).astype(float) + NormVec * self.tube_radius)
		start_point_sphere = np.array(np.array(self.coords[0:3]).astype(float) + NormVec * self.tube_radius)
		
		end_point_pipe = np.array(start_point_sphere + NormVec * (self.electrodeLen - self.tube_radius))
		end_point_sphere = np.array(self.coords[3:]).astype(float)
		
		transform = self._compute_transform(start_point_sphere, end_point_sphere, True)
		
		sphere = self._create_sphere(self.tube_radius)
		sphere = self._transform_item(sphere, transform)
		sphere.Update()

		length_pipe = np.linalg.norm(start_point_pipe - end_point_pipe)
		transform = self._compute_transform(start_point_pipe, end_point_pipe, True)
		
		pipe = self._create_pipe(length_pipe, self.tube_radius, self.tube_thickness)
		pipe = self._transform_item(pipe, transform)
		pipe.Update()
		
		self.final_model = self._combine_polydata(pipe, sphere)
		self._save_file()

	def build_seg_contact(self):
		start_point_pipe = np.array(self.coords[0:3]).astype(float)
		end_point_pipe = np.array(self.coords[3:]).astype(float)
		length_pipe = np.linalg.norm(start_point_pipe - end_point_pipe)
		transform = self._compute_transform(start_point_pipe, end_point_pipe, True)
		pipe = self._create_pipe(length_pipe, self.tube_radius, self.tube_thickness)
		trian = vtk.vtkTriangleFilter()
		trian.SetInputConnection(pipe.GetOutputPort())
		trian.Update()
		cent = [0,0,0]
		planes = vtk.vtkPlaneCollection()
		plane1 = vtk.vtkPlane()
		plane1.SetOrigin(cent[0], cent[1], cent[2])
		plane1.SetNormal(self.plane[0, :])
		planes.AddItem(plane1)
		plane2 = vtk.vtkPlane()
		plane2.SetOrigin(cent[0], cent[1], cent[2])
		plane2.SetNormal(self.plane[1, :])
		planes.AddItem(plane2)
		plane3 = vtk.vtkPlane()
		plane3.SetOrigin(cent[0], cent[1], cent[2])
		plane3.SetNormal(self.plane[2, :])
		planes.AddItem(plane3)
		clipper = vtk.vtkClipClosedSurface()
		clipper.SetInputData(trian.GetOutput())
		clipper.SetClippingPlanes(planes)
		clipper.SetScalarModeToColors()
		clipper.SetClipColor(0.89, 0.81, 0.34)
		clipper.SetBaseColor(1.0, 0.3882, 0.2784)
		clipper.SetActivePlaneColor(0.64, 0.58, 0.5)
		self.final_model = self._transform_item(clipper, transform)
		self.final_model.Update()
		self._save_file()

	def _save_file(self):
		if self.filename is not None:
			writer = vtk.vtkPolyDataWriter()
			writer.SetInputData(self.final_model.GetOutput())
			writer.SetFileName(self.filename)
			if RASsys:
				writer.SetHeader('3D Slicer output. SPACE=RAS')
			else:
				writer.SetHeader('3D Slicer output. SPACE=LPS')
			writer.Update()
			writer.Write()

	def add_to_scene(self, returnNode=False):

		if self.nodeName is not None and self.filename is None:
			node = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode')
			node.SetAndObservePolyData(self.final_model.GetOutput())
			node.SetName(self.nodeName)
			nodeDisplayNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelDisplayNode')
			node.SetAndObserveDisplayNodeID(nodeDisplayNode.GetID())
		else:
			node = slicer.util.loadModel(self.filename)
			node.SetName(os.path.splitext(os.path.splitext(os.path.basename(self.filename))[0])[0])

		if self.model_color is not None:
			if isinstance(self.model_color,str):
				self.model_color=hex2rgb(self.model_color)
			node.GetModelDisplayNode().SetColor(self.model_color)
			node.GetModelDisplayNode().SetSelectedColor(self.model_color)
		if self.model_visibility is not None:
			node.GetModelDisplayNode().SetSliceIntersectionVisibility(self.model_visibility)
			node.GetModelDisplayNode().SetSliceIntersectionOpacity(1)
			node.GetDisplayNode().Visibility2DOn()
		if [x for x in {'entry_target', 'midline', 'electrode'} if x in node.GetName()]:
			node.GetDisplayNode().SetTextScale(0)
			node.GetDisplayNode().VisibilityOff()
		if '_lead' in node.GetName():
			node.SetAttribute('ProbeEye', '1')
		if 'ses-intra' in node.GetName():
			if '_lead' in node.GetName():
				node.SetAttribute('PlanTrack', '1')
		if '_vta' in node.GetName():
			node.GetDisplayNode().SetOpacity(0.8)
		if 'type-mer' in node.GetName() and '_activity' in node.GetName():
			node.GetDisplayNode().BackfaceCullingOn()
			node.GetDisplayNode().SetSliceIntersectionThickness(2)
		if '_localizer' in node.GetName():
			node.GetDisplayNode().SetSliceIntersectionThickness(3)
		if returnNode:
			return node

class frameDetection:

	def __init__(self, node=None, derivFolder=None, frame_settings=None):

		self.derivFolder = derivFolder
		self.node = node
		self.frame_settings = frame_settings

		self.frame_center = None
		self.pointError = None
		self.pointDistanceXYZ = None
		self.meanError = None
		self.sourcePoints = None
		self.idealPoints = None
		if derivFolder is not None:
			self.frame_detect()

	def findIntersection(self, final_location):
		end_padding=5
		localizers=[]
		for axis,labels in self.frame_settings['localizer_axis'].items():
			if not isinstance(labels,list):
				labels=[labels.copy()]
			
			for ilabel in labels:
				data_cut = final_location[np.isin(final_location[:,3], ilabel)]
				line1 = [data_cut[data_cut[:,3]==ilabel[2],:3][end_padding], data_cut[data_cut[:,3]==ilabel[2],:3][-1*end_padding]]
				line2 = [data_cut[data_cut[:,3]==ilabel[1],:3][end_padding], data_cut[data_cut[:,3]==ilabel[1],:3][-1*end_padding]]
				line3 = [data_cut[data_cut[:,3]==ilabel[0],:3][end_padding], data_cut[data_cut[:,3]==ilabel[0],:3][-1*end_padding]]
				
				if axis == 'AP':
					x1 = line1[0][1]
					x2 = line1[1][1]
					x3 = line2[0][1]
					x4 = line2[1][1]
					y1 = line1[0][2]
					y2 = line1[1][2]
					y3 = line2[0][2]
					y4 = line2[1][2]
					remainder = line1[1][0]
				else:
					x1 = line1[0][0]
					x2 = line1[1][0]
					x3 = line2[0][0]
					x4 = line2[1][0]
					y1 = line1[0][2]
					y2 = line1[1][2]
					y3 = line2[0][2]
					y4 = line2[1][2]
					remainder = line1[1][1]
				
				px_top = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
				py_top = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
				
				if axis == 'AP':
					line1_top = np.array([remainder, px_top, py_top])
				else:
					line1_top = np.array([px_top, remainder, py_top])
				
				if axis == 'AP':
					x1 = line2[0][1]
					x2 = line2[1][1]
					x3 = line3[0][1]
					x4 = line3[1][1]
					y1 = line2[0][2]
					y2 = line2[1][2]
					y3 = line3[0][2]
					y4 = line3[1][2]
					remainder = line3[0][0]
				else:
					x1 = line2[0][0]
					x2 = line2[1][0]
					x3 = line3[0][0]
					x4 = line3[1][0]
					y1 = line2[0][2]
					y2 = line2[1][2]
					y3 = line3[0][2]
					y4 = line3[1][2]
					remainder = line3[0][1]
				
				px_bottom = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
				py_bottom = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4))
				
				if axis == 'AP':
					line3_bot = np.array([remainder, px_bottom, py_bottom])
					line1_bot = np.array([line1[0][0], line1[0][1], line1[0][2] - abs(line3[0][2] - line3_bot[2])])
					line3_top = np.array([line3[1][0], line3[1][1], line3[1][2] + (line1_top[2] - line1[1][2])])
				else:
					line3_bot = np.array([px_bottom, remainder, py_bottom])
					line1_bot = np.array([line1[0][0], line1[0][1], line1[0][2] - abs(line3[0][2] - line3_bot[2])])
					line3_top = np.array([line3[1][0], line3[1][1], line3[1][2] + (line1_top[2] - line1[1][2])])
				
				line1_mid=((np.array(line1_top)+np.array(line1_bot)))/2
				line3_mid=((np.array(line3_top)+np.array(line3_bot)))/2
				
				localizer_temp={}
				localizer_temp[f"bar_{self.frame_settings['localizer_labels'][ilabel[0]]}_top"]=line1_top
				localizer_temp[f"bar_{self.frame_settings['localizer_labels'][ilabel[0]]}_mid"]=line1_mid
				localizer_temp[f"bar_{self.frame_settings['localizer_labels'][ilabel[0]]}_bot"]=line1_bot
				localizer_temp[f"bar_{self.frame_settings['localizer_labels'][ilabel[2]]}_top"]=line3_top
				localizer_temp[f"bar_{self.frame_settings['localizer_labels'][ilabel[2]]}_mid"]=line3_mid
				localizer_temp[f"bar_{self.frame_settings['localizer_labels'][ilabel[2]]}_bot"]=line3_bot
				
				localizers.append(localizer_temp)
		
		return localizers

	def convert_ijk(self, points, img_obj):
		
		if isinstance(img_obj, slicer.vtkMRMLLinearTransformNode):
			affine_ijkToRas=img_obj.GetTransformToParent()
		else:
			affine_ijkToRas= vtk.vtkMatrix4x4()
			img_obj.GetIJKToRASMatrix(affine_ijkToRas)
		
		if isinstance(points,list):
			position_ijk = points + [1]
			point_Ras = affine_ijkToRas.MultiplyPoint(position_ijk)
		else:
			point_Ras=[]
			for ipoint in points:
				position_ras=np.append(np.zeros(3),1)
				position_ijk = np.append(ipoint[:3],1)
				affine_ijkToRas.MultiplyPoint(position_ijk,position_ras)
				point_Ras.append(np.hstack((position_ras[:3], ipoint[3:].tolist())))
			point_Ras=np.vstack(point_Ras)
		return point_Ras

	def flood_fill_hull(self,image):
		points = np.transpose(np.where(image))
		hull = ConvexHull(points)
		deln = Delaunay(points[hull.vertices]) 
		idx = np.stack(np.indices(image.shape), axis = -1)
		out_idx = np.nonzero(deln.find_simplex(idx) + 1)
		out_img = np.zeros(image.shape)
		out_img[out_idx] = 1
		return out_img

	def convert_ijk_mean(self, points, img_obj):
		#affine_ijkToRas = img_obj.affine.copy()
		affine_ijkToRas= vtk.vtkMatrix4x4()
		img_obj.GetIJKToRASMatrix(affine_ijkToRas)
		if isinstance(points,list):
			position_ijk = points + [1]
			point_Ras = affine_ijkToRas.MultiplyPoint(position_ijk)
		else:
			point_Ras=[]
			point_error=[]
			for islice in np.unique(points[:, 2]):
				for ilabel in np.unique(points[(points[:,2]==islice), 3]):
					npoints=len(points[(points[:,2]==islice)&(points[:,3]==ilabel), :2])
					ipoint=np.mean(points[(points[:,2]==islice)&(points[:,3]==ilabel), :2], axis=0)
					position_ijk = np.append(ipoint.tolist(),[islice, 1])
					new_points=affine_ijkToRas.MultiplyPoint(position_ijk)
					#position_ijk = ipoint.tolist() + [islice]
					#new_points = nb.affines.apply_affine(affine_ijkToRas, position_ijk)
					point_Ras.append(np.hstack((new_points[:3], ilabel, np.mean(points[(points[:,2]==islice)&(points[:,3]==ilabel), 4]),npoints)))
			point_Ras=np.vstack(point_Ras)
		return point_Ras

	def remove_leksell_mri_outlier(self,location_data):
		distance_z_max = abs(location_data[:, 2] - location_data[:,2].max())
		location_data=np.delete(location_data,np.where(distance_z_max <= 10)[0],0)
		
		distance_y_min = abs(location_data[:, 1] - location_data[:,1].min())
		location_data=np.delete(location_data,np.where(distance_y_min <= 10)[0],0)
		
		distance_x_min = abs(location_data[:, 0] - location_data[:,0].min())
		N_1_data=location_data[np.where(distance_x_min <= 25)[0]]
		
		distance_y_max = abs(location_data[:, 1] - location_data[:,1].max())
		N_2_data=location_data[np.where(distance_y_max <= 25)[0]]
		
		distance_x_max = abs(location_data[:, 0] - location_data[:,0].max())
		N_3_data=location_data[np.where(distance_x_max <= 25)[0]]
		
		location_data= np.vstack([N_1_data,N_2_data,N_3_data])

		location_data = self.remove_outlier(location_data)

		return location_data

	def remove_outlier(self,location_data):
		
		labels = np.unique(location_data[:, -1])
		final_1 = []
		for ilabel in labels:
			points = location_data[(location_data[:, -1] == ilabel)]
			if len(np.unique(points[:,2])) > 30:
				final_1.append(points)
		
		return np.vstack(final_1)

	def remove_label_outliers(self,location_data):
		final_1 = []
		for ilabel in np.unique(location_data[:,3]):
			points = location_data[(location_data[:,3] == ilabel),:]
			
			if np.std(points[:, 0]) < np.std(points[:, 1]):
				sort_idx=0
			else:
				sort_idx=1
			
			median = np.median(points[:, sort_idx])
			std = np.std(points[:, sort_idx])
			distance_from_median = abs(points[:, sort_idx] - median)
			final_1.append(points[distance_from_median < 3 * std, :])
		
		return np.vstack(final_1)

	def crw_sort(self,component):
		points = np.stack(sorted(component, key=(lambda k: k[2])))
		
		distance_y_max = abs(points[:, 1] - points[:,1].max())
		N_2_labels=np.unique(points[distance_y_max <= 30, 3])
		points=np.delete(points,np.where(np.isin(points[:,3], N_2_labels))[0],0)
		
		distance_from_min = abs(points[:, 0] - points[:,0].min())
		N_1_labels=np.unique(points[distance_from_min <= 30, 3])
		points=np.delete(points,np.where(np.isin(points[:,3], N_1_labels))[0],0)
		
		distance_from_max = abs(points[:, 0] - points[:,0].max())
		N_3_labels=np.unique(points[distance_from_max <= 30, 3])
		points=np.delete(points,np.where(np.isin(points[:,3], N_3_labels))[0],0)
		
		component_old=component.copy()
		component[np.isin(component_old[:,3], N_1_labels),3]=1
		component[np.isin(component_old[:,3], N_2_labels),3]=2
		component[np.isin(component_old[:,3], N_3_labels),3]=3
		
		combined_tmp=[]
		label_cnt=1
		for label in np.unique(component[:,3]):
			sort_idx=0
			if component[component[:,3]==label,0].std() < component[component[:,3]==label,1].std():
				sort_idx=1
			for ind in np.unique(component[(component[:,3]==label),2]):
				points=component[(component[:,3]==label)&(component[:,2]==ind),:3]
				points = np.stack(sorted(points, key=(lambda k: k[sort_idx])))
				gaps = [[s, e] for s, e in zip(points[:,sort_idx], points[:,sort_idx][1:]) if s+2 < e]
				if len(gaps)==2:
					bar_1=points[points[:,sort_idx]<=gaps[0][0],:3]
					bar_2=points[(points[:,sort_idx]>=gaps[0][1])&(points[:,sort_idx]<=gaps[1][0]),:3]
					bar_3=points[points[:,sort_idx]>=gaps[1][1],:3]
					
					combined_tmp.append(np.vstack((np.c_[bar_1,np.repeat(label_cnt,len(bar_1))],
								   np.c_[bar_2,np.repeat(label_cnt+1,len(bar_2))],
								   np.c_[bar_3,np.repeat(label_cnt+2,len(bar_3))])))
			
			label_cnt+=3
		
		combined_tmp=np.vstack(combined_tmp)
		
		mask1 = combined_tmp[np.isin(combined_tmp[:,-1], [1,2,3]),:]
		gaps = [[s, e] for s, e in zip(mask1[:,2], mask1[:,2][1:]) if s+5 < e]
		mask1=mask1[mask1[:,2]>=gaps[0][1],:]
		
		mask2 = combined_tmp[np.isin(combined_tmp[:,-1], [7,8,9]),:]
		gaps = [[s, e] for s, e in zip(mask2[:,2], mask2[:,2][1:]) if s+5 < e]
		mask2=mask2[mask2[:,2]>=gaps[0][1],:]
		
		combined=np.r_[mask1,combined_tmp[np.isin(combined_tmp[:,-1], [4,5,6]),:],mask2]
		unq_zslice=np.unique(combined[:,2])
		combined=combined[combined[:,2]> np.unique(combined[:,2]).min()+len(unq_zslice)*.15]
		
		return combined

	def NLocalizersSort(self,component,ncomponents, imethod):
		points = np.stack(sorted(component, key=(lambda k: k[2])))
		
		AP_index=1
		ML_index=0

		if ncomponents==2:
			sort_idx=0
			if component[:,0].std() < component[:,1].std():
				sort_idx=1
			
			distance_sort_max = abs(points[:, sort_idx] - points[:,sort_idx].max())
			gaps = [[s, e] for s, e in zip(sorted(distance_sort_max), sorted(distance_sort_max)[1:]) if s+15 < e]
			# pick the first gap for the anterior N-localizer
			min_threshold=gaps[0][0]
			N_2_points=points[distance_sort_max <= min_threshold, :3]
			points=np.delete(points,np.where(distance_sort_max <= min_threshold)[0],0)
			N_2_points=np.c_[N_2_points, [2]*len(N_2_points)]
			
			distance_from_min = abs(points[:,sort_idx] - points[:,sort_idx].min())
			gaps = [[s, e] for s, e in zip(sorted(distance_from_min), sorted(distance_from_min)[1:]) if s+15 < e]
			# since only points associated with the last localizer should be present the gaps list should be empty
			# if it's not empty then pick only the points meeting the threshold, the remainder are noise
			if gaps:
				# pick the first gap for the anterior N-localizer
				min_threshold=gaps[0][0]
				N_1_points=points[distance_from_min <= min_threshold, :3]
			else:
				N_1_points=points[:,:3]
			
			N_1_points=np.c_[N_1_points, [1]*len(N_1_points)]
			
			component=np.r_[N_1_points, N_2_points]
			
		elif ncomponents>2:
			if imethod == 1:
				thres_val=10
			else:
				thres_val=15
			# find distance from max in y-axis
			distance_AP_max = abs(points[:, AP_index] - points[:,AP_index].max())
			# identiy the gaps in distances greater than 9 voxels (these are seperate bars)
			gaps = [[s, e] for s, e in zip(sorted(distance_AP_max), sorted(distance_AP_max)[1:]) if s+thres_val < e]
			# pick the first gap for the anterior N-localizer
			min_threshold=gaps[0][0]
			AP_points=points[distance_AP_max <=min_threshold, :]
			points=np.delete(points,np.where(distance_AP_max <= min_threshold)[0],0)
			AP_points=np.c_[AP_points, [2]*len(AP_points)]
			
			if imethod == 1:
				thres_val=10
				ML_label=1
			else:
				thres_val=3
				ML_label=3
			distance_ML_min = abs(points[:,ML_index] - points[:,ML_index].min())
			gaps = [[s, e] for s, e in zip(sorted(distance_ML_min), sorted(distance_ML_min)[1:]) if s+thres_val < e]
			# pick the first gap for the anterior N-localizer
			min_threshold=gaps[0][0]
			ML1_points=points[distance_ML_min <= min_threshold, :]
			if len(ML1_points) <1000 and len(gaps) > 1 and imethod==2:
				min_threshold=gaps[0][0]
				ML1_points=points[(distance_ML_min > gaps[0][0]) & (distance_ML_min <= gaps[1][0]), :]
				points=np.delete(points,np.where((distance_ML_min > gaps[0][0]) & (distance_ML_min <= gaps[1][0]))[0],0)
			else:
				points=np.delete(points,np.where(distance_ML_min <= min_threshold)[0],0)

			ML1_points=np.c_[ML1_points, [ML_label]*len(ML1_points)]
			

			if imethod == 1:
				distance_ML_max = abs(points[:,ML_index] - points[:,ML_index].max())
				ML_label=3
			else:
				distance_ML_max = abs(points[:,ML_index] - np.median(points[:,ML_index]))
				ML_label=1
			gaps = [[s, e] for s, e in zip(sorted(distance_ML_max), sorted(distance_ML_max)[1:]) if s+10 < e]
			# since only points associated with the last localizer should be present the gaps list should be empty
			# if it's not empty then pick only the points meeting the threshold, the remainder are noise
			if gaps:
				# pick the first gap for the anterior N-localizer
				min_threshold=gaps[0][0]
				ML2_points=points[distance_ML_max <= min_threshold, :]
			else:
				ML2_points=points[:,:]
			
			ML2_points=np.c_[ML2_points, [ML_label]*len(ML2_points)]
			
			component=np.r_[AP_points, ML1_points,ML2_points]
		
		combined=[]
		for label in np.unique(component[:,-1]):
			sort_idx=0
			if component[component[:,-1]==label,0].std() < component[component[:,-1]==label,1].std():
				sort_idx=1
			clust_tmp=[]
			for ind in np.unique(component[(component[:,-1]==label),2]):
				points=component[(component[:,-1]==label)&(component[:,2]==ind),:]
				points = np.stack(sorted(points, key=(lambda k: k[sort_idx])))
				gaps = [[s, e] for s, e in zip(points[:,sort_idx], points[:,sort_idx][1:]) if s+1 < e]
				if len(gaps)==2:
					bar_1=points[points[:,sort_idx]<=gaps[0][0],:]
					bar_2=points[(points[:,sort_idx]>=gaps[0][1])&(points[:,sort_idx]<=gaps[1][0]),:]
					bar_3=points[points[:,sort_idx]>=gaps[1][1],:]
					
					if label==1:
						label_start=1
					elif label==2:
						label_start=4
					elif label==3:
						label_start=7
					
					clust_tmp.append(np.vstack((np.c_[bar_1,np.repeat(label_start,len(bar_1))],
								   np.c_[bar_2,np.repeat(label_start+1,len(bar_2))],
								   np.c_[bar_3,np.repeat(label_start+2,len(bar_3))])))
			if clust_tmp:
				mask=np.vstack(clust_tmp)
			
				#if imethod == 1:
				#	frame_bot=np.array([np.mean(mask[:,2])-61,mask[:,2].min()]).max()
				#	frame_top=np.array([np.mean(mask[:,2])+61,mask[:,2].max()]).min()
				#	combined.append(mask[(mask[:,2]>=frame_bot) & (mask[:,2]<=frame_top),:])
				#else:
				combined.append(mask)

		combined=np.vstack(combined)
		return combined

	def determineImageThreshold(self, img_data):
		
		hist_y, hist_x = np.histogram(img_data.flatten(), bins=256)
		hist_x = hist_x[0:-1]
		
		cumHist_y = np.cumsum(hist_y.astype(float))/np.prod(np.array(img_data.shape))
		# The background should contain half of the voxels
		minThreshold_byCount = hist_x[np.where(cumHist_y > 0.90)[0][0]]
		
		hist_diff = np.diff(hist_y)
		hist_diff_zc = np.where(np.diff(np.sign(hist_diff)) == 2)[0].flatten()
		minThreshold = hist_x[hist_diff_zc[hist_x[hist_diff_zc] > (minThreshold_byCount)][0]]
		print(f"first maxima after soft tissue found: {minThreshold}")
		
		return minThreshold

	def frame_detect(self):
		imethod=1
		if imethod == 1:
			img_data_kji = slicer.util.arrayFromVolume(self.node).copy()
			img_data = np.transpose(img_data_kji, (2, 1, 0))
			pix_dim = self.node.GetSpacing()

			image_type=None
			if not img_data_kji.min() < 0:
				image_type='mri'

				lmin = float(img_data.min())
				lmax = float(img_data.max())
				norm_img=np.floor((img_data-lmin)/(lmax-lmin) * 255.)

				thresh_img = norm_img > norm_img.mean()
				thresh_img = ndimage.binary_fill_holes(thresh_img)

				thres_min = threshold_otsu(thresh_img)
				boolean_binary = (thresh_img > thres_min)
				binary = 1 * boolean_binary

				structEle = int(np.ceil(2 / max(pix_dim)))+1
				morph_image = morphology.binary_erosion(thresh_img, morphology.ball(structEle))
				morph_image = morphology.binary_dilation(morph_image, morphology.ball(structEle))
				masked_image = np.invert(morph_image)*thresh_img

				#labels, n_labels = measure.label(binary, background=0, return_num=True)
				#label_count = np.bincount(labels.ravel().astype(np.int))
				#label_count[0] = 0
	#
	#			#mask = labels == label_count.argmax()
	#			#mask = ndimage.morphology.binary_fill_holes(mask)
	#			#masked_image = np.invert(mask)*binary
	#
	#			#labels, n_labels = measure.label(masked_image, background=0, return_num=True)
	#			#properties = measure.regionprops(labels)
	#			#properties.sort(key=lambda x: x.area, reverse=True)
				#areas=np.array([prop.area for prop in properties])
			else:
				image_type='ct'

				img_data[img_data < -1024] = -1024
				img_data[img_data > 3071] = 3071

				if self.frame_settings['max_threshold'] == 'n/a':
					thresh_img = (img_data > self.frame_settings['min_threshold'])
				else:
					thresh_img = (img_data > self.frame_settings['min_threshold'])&(img_data < self.frame_settings['max_threshold'])
				
				if any (x==self.frame_settings['system'] for x in ('leksell','leksellg','crw')):
					structEle=int(np.ceil(2 / max(pix_dim)))+1
					if self.frame_settings['system'] == 'crw':
						eroded_image = morphology.binary_erosion(thresh_img,np.ones((structEle,structEle,structEle)))
						morph_image = morphology.binary_dilation(eroded_image, np.ones((structEle,structEle,structEle)))
					else:
						eroded_image = morphology.binary_erosion(thresh_img, morphology.ball(structEle))
						morph_image = morphology.binary_dilation(eroded_image, morphology.ball(structEle))
					morph_image = morphology.binary_dilation(morph_image,np.ones((5,5,5)))
					morph_image = morphology.binary_dilation(morph_image,np.ones((5,5,5)))
					masked_image = np.invert(morph_image)*thresh_img
				else:
					structEle=int(np.ceil(2 / max(pix_dim)))
					eroded_image = morphology.binary_erosion(thresh_img, np.ones((structEle,structEle,structEle)))
					morph_image=self.flood_fill_hull(eroded_image)
					morph_image=morphology.binary_erosion(morph_image, morphology.ball(5))
					morph_image=morphology.binary_erosion(morph_image, morphology.ball(5))
					morph_image=morphology.binary_erosion(morph_image, morphology.ball(5))
					masked_image = np.invert(morph_image)*thresh_img

				#labels, n_labels = measure.label(segmentation, background=0, return_num=True)
				#label_count = np.bincount(labels.ravel().astype(np.int))
				#label_count[0] = 0
				#
				#mask = labels == label_count.argmax()
				#mask = ndimage.morphology.binary_fill_holes(mask)
				#masked_image = np.invert(mask)*thresh_img

			labels, n_labels = measure.label(masked_image, background=0, return_num=True)
			properties = measure.regionprops(labels)
			properties.sort(key=lambda x: x.area, reverse=True)
			areas=np.array([prop.area for prop in properties])
			
			#areas[0] = 0
			#largeComponentsIdx = [int(x) for x in np.where(areas >=self.frame_settings['min_size'])[0]]

			largeComponentsIdx = [int(x) for x in np.where(np.logical_and(areas >= self.frame_settings['min_size'], areas< self.frame_settings['max_size']))[0]]

			voxelCoords=[np.array(properties[x].coords) for x in largeComponentsIdx]
			voxel_info=np.vstack([np.c_[voxelCoords[x],np.repeat(x+1, len(voxelCoords[x]))] for x in range(len(largeComponentsIdx))])
			
			if image_type == 'mri' and 'leksellg' in self.frame_settings['system']:
				voxel_info=self.remove_leksell_mri_outlier(voxel_info)
			else:
				voxel_info=self.remove_outlier(voxel_info)

			if any (x==self.frame_settings['system'] for x in ('leksellg','crw')):
				voxel_info=self.NLocalizersSort(voxel_info, self.frame_settings['n_components'], 1)

			voxel_info[:,3]=np.array([self.frame_settings['labels'][x] for x in voxel_info[:,5]])
			voxel_info=np.vstack([voxel_info[voxel_info[:,2]==x, :] for x in np.unique(voxel_info[:, 2]) if set(voxel_info[voxel_info[:,2]==x, 3]) == set(self.frame_settings['labels'])])
			voxel_info=np.c_[voxel_info,np.array([int(img_data[x[0],x[1],x[2]]) for x in voxel_info])]
			
			self.final_location_clusters=self.convert_ijk(voxel_info,self.node)
			final_location=self.convert_ijk_mean(voxel_info,self.node)
			self.final_location=self.remove_label_outliers(final_location)

		elif imethod == 2:
			import SimpleITK as sitk

			img_obj = sitk.ReadImage(self.node.GetStorageNode().GetFileName())
			img_obj = sitk.PermuteAxes(img_obj, [2,1,0])
			img_data = sitk.GetArrayFromImage(img_obj)
			voxsize = img_obj.GetSpacing()

			minThreshold=self.determineImageThreshold(img_data)
			thresh_img = img_obj > minThreshold

			stats = sitk.LabelShapeStatisticsImageFilter()
			stats.SetComputeOrientedBoundingBox(True)
			stats.Execute(thresh_img)

			connectedComponentImage = sitk.ConnectedComponent(thresh_img, False)
			stats.Execute(connectedComponentImage)

			labelBBox_size_mm = np.array([stats.GetOrientedBoundingBoxSize(l) for l in stats.GetLabels()])*voxsize
			labelBBox_center_mm = np.array([np.array(stats.GetOrientedBoundingBoxOrigin(l)) + np.dot(np.reshape(stats.GetOrientedBoundingBoxDirection(l), [3,3]),
											(np.array(stats.GetOrientedBoundingBoxSize(l))*voxsize)/2  ) for l in stats.GetLabels()])

			allObjects_bboxCenter = np.array(stats.GetCentroid(1))
			allObjects_bboxSize = np.array(stats.GetOrientedBoundingBoxSize(1))*voxsize

			labelBBoxCentroidDistFromCenter = np.linalg.norm(labelBBox_center_mm - np.tile(allObjects_bboxCenter, [labelBBox_center_mm.shape[0], 1]), axis=1)
			objectMajorAxisSize_mask = np.sum(labelBBox_size_mm > allObjects_bboxSize*0.5, axis=1 )>0

			compacityRatio_mask = np.sum(np.stack([labelBBox_size_mm[:,0]/labelBBox_size_mm[:,1],
												   labelBBox_size_mm[:,1]/labelBBox_size_mm[:,2],
												   labelBBox_size_mm[:,2]/labelBBox_size_mm[:,0]], axis=1)>4, axis=1 )>0

			centroidDist_mask = labelBBoxCentroidDistFromCenter > np.min(allObjects_bboxSize)*0.3

			print("%d objects left after objectMajorAxisSize_mask"%(np.sum(objectMajorAxisSize_mask==1)))
			print("%d objects left after compacityRatio_mask"%(np.sum(compacityRatio_mask*objectMajorAxisSize_mask==1)))
			print("%d objects left after centroidDist_mask"%(np.sum(centroidDist_mask*compacityRatio_mask*objectMajorAxisSize_mask==1)))

			labelToKeep_mask = objectMajorAxisSize_mask * compacityRatio_mask * centroidDist_mask
			connected_labelMap = sitk.LabelImageToLabelMap(connectedComponentImage)

			label_renameMap = sitk.DoubleDoubleMap()
			for i, toKeep in enumerate(labelToKeep_mask):
				if not toKeep:
					label_renameMap[i+1]=0

			newLabelMap = sitk.ChangeLabelLabelMap(connected_labelMap, label_renameMap)
			stats.Execute(sitk.LabelMapToLabel(newLabelMap))


			coords = {label:np.where(sitk.GetArrayFromImage(connectedComponentImage) == label) for label in stats.GetLabels()}
			component=[]
			for icoord in coords:
				physical_points = np.stack([[int(x), int(y), int(z)] for x,y,z in zip(coords[icoord][0], coords[icoord][1], coords[icoord][2])])
				physical_intensity = np.stack([img_data[int(x), int(y), int(z)] for x,y,z in zip(coords[icoord][0], coords[icoord][1], coords[icoord][2])])
				component.append(np.c_[physical_points, np.repeat(icoord,len(physical_points)), physical_intensity])

			component=np.vstack(component)

			combined=self.NLocalizersSort(component, self.frame_settings['n_components'], 2)

			combined[:,3]=combined[:,-1]
			combined = combined[:,list(range(combined.shape[1]-1))]
			
			self.final_location_clusters=self.convert_ijk(combined, self.node)
			final_location=self.convert_ijk_mean(combined, self.node)
			self.final_location=self.remove_label_outliers(final_location)


		fcsvNodeName = f"{self.derivFolder.split(os.path.sep)[-1]}_desc-%s_fids"

		models = slicer.util.getNodesByClass('vtkMRMLMarkupsFiducialNode')
		for i in models:
			if any(i.GetName() == x for x in  (fcsvNodeName % ('fiducials'),fcsvNodeName % ('topbottom'))):
				slicer.mrmlScene.RemoveNode(slicer.util.getNode(i.GetName()))

		fidNodeFrame=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
		fidNodeFrame.SetName(fcsvNodeName % ('fiducials'))
		fidNodeFrame.AddDefaultStorageNode()
		fidNodeFrame.GetStorageNode().SetCoordinateSystem(0)
		fidNodeFrame.GetDisplayNode().SetGlyphScale(0.1)
		fidNodeFrame.GetDisplayNode().SetTextScale(6.5)
		fidNodeFrame.GetDisplayNode().SetColor(0.333, 1, 0.490)
		fidNodeFrame.GetDisplayNode().SetSelectedColor(1, 0, 0)
		wasModify=fidNodeFrame.StartModify()
		labels=[]
		for ipoint in self.final_location:
			n = fidNodeFrame.AddControlPoint(vtk.vtkVector3d(ipoint[0], ipoint[1], ipoint[2]))
			fidNodeFrame.SetNthControlPointLabel(n, f"P{int(ipoint[3])}")
			if f"P{int(ipoint[3])}" not in labels: labels.append(f"P{int(ipoint[3])}")


		fidNodeFrame.EndModify(wasModify)

		#slicer.util.saveNode(fidNodeFrame, os.path.join(self.derivFolder, 'frame', fcsvNodeName % ('fiducials') + '.fcsv'))
		
		values = self.findIntersection(self.final_location)

		fidNodeFrame2=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
		fidNodeFrame2.SetName(fcsvNodeName % ('topbottom'))
		fidNodeFrame2.AddDefaultStorageNode()
		fidNodeFrame2.GetStorageNode().SetCoordinateSystem(coordSys)
		fidNodeFrame2.GetDisplayNode().SetGlyphScale(0.8)
		fidNodeFrame2.GetDisplayNode().SetTextScale(6.5)
		fidNodeFrame2.GetDisplayNode().SetSelectedColor(1, 0, 0)
		wasModify=fidNodeFrame2.StartModify()
		for ilocalizer in values:
			for ilabel,ipoint in ilocalizer.items():
				n = fidNodeFrame2.AddControlPoint(vtk.vtkVector3d(ipoint[0], ipoint[1], ipoint[2]))
				fidNodeFrame2.SetNthControlPointLabel(n, ilabel)

		fidNodeFrame2.EndModify(wasModify)
		fidNodeFrame2.GetDisplayNode().SetVisibility(0)

		#slicer.util.saveNode(fidNodeFrame2, os.path.join(self.derivFolder, 'frame', fcsvNodeName % ('topbottom') + '.fcsv'))

		self.frame_center = getFrameCenter(self.frame_settings['system'])

		frameCenterNode = slicer.util.getNode('frame_center')
		frameCenterNode.GetDisplayNode().SetVisibility(0)
		
		models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
		for imodel in models:
			if f"space-{self.frame_settings['system']}_label-" in imodel.GetName():
				slicer.mrmlScene.RemoveNode(slicer.util.getNode(imodel.GetID()))

		if circleFrameFiducials:
			vtkModelBuilder = vtkModelBuilderClass()
			vtkModelBuilder.tube_radius = self.frame_settings['localizer_bar_radius']
			vtkModelBuilder.tube_thickness = self.frame_settings['localizer_bar_radius']
			vtkModelBuilder.model_color = (1, 0, 0)
			vtkModelBuilder.model_visibility = True

		vtkModelBuilder2 = vtkModelBuilderClass()
		vtkModelBuilder2.tube_radius = 0.5
		vtkModelBuilder2.tube_thickness = 0.5
		vtkModelBuilder2.model_color = (1, 0, 0)
		vtkModelBuilder2.model_visibility = False
		
		if any(x == self.frame_settings['system'] for x in ('leksellg','brw','crw')) and frame_align:
			transformType = 0
			numIterations = 100

			transformDesc='rigid'
			if self.frame_settings['settings']['parameters']['transformType']==1:
				transformDesc='sim'
			elif self.frame_settings['settings']['parameters']['transformType']==2:
				transformDesc='affine'
			
			outputTransformPrefix = f"{self.derivFolder.split(os.path.sep)[-1]}_desc-{transformDesc}_from-fiducials_to-localizer_xfm"
			outputModelPrefix = f"{self.derivFolder.split(os.path.sep)[-1]}_space-{self.frame_settings['system']}_label-all_localizer"
			
			inputTransform = slicer.vtkMRMLLinearTransformNode()
			inputTransform.SetName(outputTransformPrefix)
			slicer.mrmlScene.AddNode(inputTransform)

			#models = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
			#for imodel in models:
			#	if f"space-{self.frame_settings['system']}_label-" in imodel.GetName():
			#		imodel.SetAndObserveTransformNodeID(inputTransform.GetID())

			#### convert detected fiducials to Polydata
			inputFiducials = slicer.util.getNode(fcsvNodeName % ('fiducials'))
			inputPolyData = convertMarkupsToPolyData(inputFiducials)

			#### construct frame target Polydata
			targetModelGlyphName=f"{self.derivFolder.split(os.path.sep)[-1]}_space-{self.frame_settings['system']}_acq-glyph_label-all_localizer"
			targetModelTubeName=f"{self.derivFolder.split(os.path.sep)[-1]}_space-{self.frame_settings['system']}_acq-tube_label-all_localizer"
			inputTargetModel,frameTubeNode,tubePolyData=targetFrameObject(inputFiducials, self.frame_settings['system'], targetModelGlyphName, targetModelTubeName)

			#### set output ICP transform prior to running registration
			fidNodeTB = slicer.util.getNode(fcsvNodeName % ('topbottom'))
			fidNodeTB.SetAndObserveTransformNodeID(inputTransform.GetID())
			fidNodeFC = slicer.util.getNode('frame_center')
			fidNodeFC.SetAndObserveTransformNodeID(inputTransform.GetID())
			inputFiducials.SetAndObserveTransformNodeID(inputTransform.GetID())
			self.node.SetAndObserveTransformNodeID(inputTransform.GetID())

			#### run ICP registration
			inputTransform = runFrameModelRegistration(inputPolyData, tubePolyData, inputTransform, **self.frame_settings['settings']['parameters'])
			
			#### apply the transform to the floating Polydata
			#if self.frame_settings['settings']['parameters']['reverseSourceTar']:
			#	frameTubeNode.SetAndObserveTransformNodeID(inputTransform.GetID())
			#	#frameTubeNode.SetAndObserveTransformNodeID(inputTransform.GetID())
			#else:
			inputPolyData.SetAndObserveTransformNodeID(inputTransform.GetID())

			#### compute RMSE
			self.meanError, self.pointError, self.pointDistanceXYZ, self.sourcePoints, self.idealPoints = ComputeMeanDistance(inputPolyData, tubePolyData,inputTransform)

			self.final_location_clusters = self.convert_ijk(self.final_location_clusters, inputTransform)
			self.final_location_clusters = self.final_location_clusters[np.lexsort((self.final_location_clusters[:,2],self.final_location_clusters[:,3]))]

		self.frame_center = getFrameCenter(self.frame_settings['system'])


def targetFrameObject(inputFiducials, frame_system, targetModelGlyphName, targetModelTubeName):
	"""Construct stereotactic frame Polydata.

	Parameters
	----------
	inputFiducials : vtkMRMLMarkupsFiducialNode
		A list of the fiducial point centers detected in the frame volume.

	frame_system : str
		The name of the stereotactic frame system used.

	targetModelName : str
		The name for the output frame model node.

	Returns
	-------
	frameGlyphNode : vtkMRMLMModelNode
		A Glyph representation of the stereotactic frame system (used for ICP)

	frameTubeNode : vtkMRMLMModelNode
		A tube representation of the stereotactic frame system (saved to disk)

	"""
	num_points=int(inputFiducials.GetNumberOfControlPoints()/9)
	if 'leksell' in frame_system:
		origin=np.array([100,100,100])
		x_min=95
		y_min=60
		origin_z=-160
		n_height=120
		n_width=120
		total_width=190
		anteriorBar_xmin=35
		anteriorBar_ymax=55
		frameSystemPoints={
			'localizer_3':{
				'c': {
						'top':[x_min-total_width, y_min, (origin[0]+origin_z)+n_height],
						'bot':[x_min-total_width, y_min, origin[0]+origin_z],
					},
				'mid':{
					'top':'a',
					'bot':'c'
				},
				'a': {
					'top':[x_min-total_width, y_min-n_width, (origin[0]+origin_z)+n_height],
					'bot':[x_min-total_width, y_min-n_width, origin[0]+origin_z],
				}
			},
			'localizer_2':{
				'c': {
					'top':[x_min-anteriorBar_xmin, y_min+anteriorBar_ymax, (origin[0]+origin_z)+n_height],
					'bot':[x_min-anteriorBar_xmin, y_min+anteriorBar_ymax, origin[0]+origin_z]
				},
				'mid':{
					'top':'c',
					'bot':'a'
				},
				'a': {
					'top':[(x_min-anteriorBar_xmin)-n_width, y_min+anteriorBar_ymax, (origin[0]+origin_z)+n_height],
					'bot':[(x_min-anteriorBar_xmin)-n_width, y_min+anteriorBar_ymax, origin[0]+origin_z]
				}
			},
			'localizer_1':{
				'c': {
						'top':[x_min, y_min, (origin[0]+origin_z)+n_height],
						'bot':[x_min, y_min, origin[0]+origin_z],
				},
				'mid':{
					'top':'a',
					'bot':'c'
				},
				'a': {
					'top':[x_min, y_min-n_width, (origin[0]+origin_z)+n_height],
					'bot':[x_min, y_min-n_width, origin[0]+origin_z],
				}
			}
		}
	elif 'brw'  in frame_system:
		origin=np.array([0,0,0])
		x_min=70
		y_min=121.25
		origin_z=-86
		n_height=189
		n_width=140
		frameSystemPoints={
			'localizer_3':{
				'c': {
					'bot':[x_min*-1, origin[1]-y_min, origin_z],
					'top':[x_min*-1, origin[1]-y_min, origin_z+n_height]
					
				},
				'mid':{
					'top':'a',
					'bot':'c'
				},
				'a': {
					'bot':[x_min, origin[1]-y_min, origin_z],
					'top':[x_min, origin[1]-y_min, origin_z+n_height]
				}
			},
			'localizer_2':{
				'c': {
					'bot':[x_min, y_min, origin_z],
					'top':[x_min, y_min, origin_z+n_height]
				},
				'mid':{
					'top':'c',
					'bot':'a'
				},
				'a': {
					'bot':[n_width, 0, origin_z],
					'top':[n_width, 0, origin_z+n_height]
				}
			},
			'localizer_1':{
				'a': {
					'bot':[x_min-n_width, y_min, origin_z],
					'top':[x_min-n_width, y_min, origin_z+n_height]
				},
				'mid':{
					'top':'c',
					'bot':'a'
				},
				'c': {
					'bot':[x_min-x_min-n_width, 0, origin_z],
					'top':[x_min-x_min-n_width, 0, origin_z+n_height]
				}
			}
		}
	elif 'crw' in frame_system:
		origin=np.array([0,0,0])
		x_min=100
		y_min=60
		origin_z=-60
		n_height=120
		n_width=120
		total_width=200
		anteriorBar_xmin=40
		anteriorBar_ymax=45

		frameSystemPoints={
			'localizer_3':{
				'c': {
						'top':[x_min-total_width, y_min, (origin[0]+origin_z)+n_height],
						'bot':[x_min-total_width, y_min, origin[0]+origin_z],
					},
				'mid':{
					'top':'a',
					'bot':'c'
				},
				'a': {
					'top':[x_min-total_width, y_min-n_width, (origin[0]+origin_z)+n_height],
					'bot':[x_min-total_width, y_min-n_width, origin[0]+origin_z],
				}
			},
			'localizer_2':{
				'c': {
					'top':[x_min-anteriorBar_xmin, y_min+anteriorBar_ymax, (origin[0]+origin_z)+n_height],
					'bot':[x_min-anteriorBar_xmin, y_min+anteriorBar_ymax, origin[0]+origin_z]
				},
				'mid':{
					'top':'a',
					'bot':'c'
				},
				'a': {
					'top':[(x_min-anteriorBar_xmin)-n_width, y_min+anteriorBar_ymax, (origin[0]+origin_z)+n_height],
					'bot':[(x_min-anteriorBar_xmin)-n_width, y_min+anteriorBar_ymax, origin[0]+origin_z]
				}
			},
			'localizer_1':{
				'c': {
						'top':[x_min, y_min, (origin[0]+origin_z)+n_height],
						'bot':[x_min, y_min, origin[0]+origin_z],
				},
				'mid':{
					'top':'c',
					'bot':'a'
				},
				'a': {
					'top':[x_min, y_min-n_width, (origin[0]+origin_z)+n_height],
					'bot':[x_min, y_min-n_width, origin[0]+origin_z],
				}
			}
		}

	fidNodeFrame=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
	fidNodeFrame.SetName('frameSystemFiducials')
	fidNodeFrame.AddDefaultStorageNode()
	wasModify=fidNodeFrame.StartModify()

	appenderTube = vtk.vtkAppendPolyData()
	for fiducialIndex in frameSystemPoints.keys():
		framePointsVTK = vtk.vtkPoints()
		sourceVertices = vtk.vtkCellArray()
		#### loop through each N-localizer
		for iLine in frameSystemPoints[fiducialIndex].keys():
			#### if its a middle (diagonal) bar then shapely will use all dimensions (3D)
			if iLine == 'mid':
				indexTop=frameSystemPoints[fiducialIndex][iLine]['top']
				indexBot=frameSystemPoints[fiducialIndex][iLine]['bot']
				top=np.array(frameSystemPoints[fiducialIndex][indexTop]['top'])
				bot=np.array(frameSystemPoints[fiducialIndex][indexBot]['bot'])
			#### if its a vertical bar then shapely will use only 2 dimensions
			else:
				top=np.array(frameSystemPoints[fiducialIndex][iLine]['top'])
				bot=np.array(frameSystemPoints[fiducialIndex][iLine]['bot'])
			#### interpolate points between the start and end of the N-localizer bar
			for ipoint in np.vstack([np.linspace(float(top[dim]),float(bot[dim]),num_points+9) for dim in range(3)]).T:
				n = fidNodeFrame.AddControlPoint(vtk.vtkVector3d(ipoint[0], ipoint[1], ipoint[2]))
				fidNodeFrame.SetNthControlPointLabel(n, f"P{int(ipoint[2])}")
			#### interpolate points between the start and end of the N-localizer bar
			for ipoint in np.vstack([np.linspace(float(top[dim]),float(bot[dim]),2) for dim in range(3)]).T:
				framePointsVTK.InsertNextPoint(int(ipoint[0]), int(ipoint[1]), int(ipoint[2]))
			#### construct Polydata lines for tube filter
			lines = vtk.vtkCellArray()
			for i in range(framePointsVTK.GetNumberOfPoints()-1):
				polyLine = vtk.vtkLine()
				polyLine.GetPointIds().SetId(0, i)
				polyLine.GetPointIds().SetId(1, i + 1)
				lines.InsertNextCell(polyLine)
			#### append the points/lines for tube filter
			tubePolyData = vtk.vtkPolyData()
			tubePolyData.SetPoints(framePointsVTK)
			tubePolyData.SetLines(lines)
			appenderTube.AddInputData(tubePolyData)
			appenderTube.Update()

	fidNodeFrame.EndModify(wasModify)

	frameGlyphNode=convertMarkupsToPolyData(fidNodeFrame, node_name=targetModelGlyphName)
	slicer.mrmlScene.RemoveNode(fidNodeFrame)

	# display the polydata as tubes
	tubeFilter = vtk.vtkTubeFilter()
	tubeFilter.SetInputConnection(appenderTube.GetOutputPort())
	tubeFilter.SetRadius(0.1)
	tubeFilter.SetNumberOfSides(25)
	tubeFilter.Update()

	frameTubeNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode')
	frameTubeNode.CreateDefaultDisplayNodes()
	frameTubeNode.SetAndObservePolyData(tubeFilter.GetOutput())
	frameTubeNode.GetDisplayNode().SetVisibility(0)
	frameTubeNode.GetDisplayNode().SetVisibility2D(0)
	frameTubeNode.GetDisplayNode().SetColor(1,0.666,0)
	frameTubeNode.GetDisplayNode().SetEdgeColor(1,0.666,0)
	frameTubeNode.GetDisplayNode().SetRepresentation(2)
	frameTubeNode.GetDisplayNode().SetLineWidth(1)
	frameTubeNode.GetDisplayNode().LightingOff()
	frameTubeNode.SetName(targetModelTubeName)

	return frameGlyphNode,frameTubeNode,appenderTube

def convertMarkupsToPolyData(inputFiducials, node_name=None):
	"""Converts markups to polydata.

	Parameters
	----------
	inputFiducials : vtkMRMLMarkupsFiducialNode
		A list of the fiducial point centers detected in the frame volume.

	Returns
	-------
	sourceGlyphNode : vtkMRMLMModelNode
		A Glyph representation of the detected fiducials in the input volume.
	
	"""
	framePointsVTK = vtk.vtkPoints()
	sourceVertices = vtk.vtkCellArray()
	for fiducialIndex in range(inputFiducials.GetNumberOfControlPoints()):
		p = np.zeros(3)
		inputFiducials.GetNthControlPointPositionWorld(fiducialIndex, p)
		id=framePointsVTK.InsertNextPoint(p[0],p[1],p[2])
		sourceVertices.InsertNextCell(1)
		sourceVertices.InsertCellPoint(id)

	pointPolyData = vtk.vtkPolyData()
	pointPolyData.SetPoints(framePointsVTK)
	pointPolyData.SetVerts(sourceVertices)

	#### display polydata as glyphs
	glyphFilter = vtk.vtkVertexGlyphFilter()
	glyphFilter.AddInputData(pointPolyData)
	glyphFilter.Update()

	sourceGlyphNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode')
	sourceGlyphNode.CreateDefaultDisplayNodes()
	sourceGlyphNode.SetAndObservePolyData(glyphFilter.GetOutput())
	if node_name is not None:
		sourceGlyphNode.SetName(node_name)
	else:
		sourceGlyphNode.SetName('sourceFiducialModel')
	sourceGlyphNode.GetDisplayNode().SetRepresentation(0)

	return sourceGlyphNode

def ComputeMeanDistance(inputSourceModel, inputTargetModel, icpTransform):
	"""Computes the RMSE from ICP registration.

	Parameters
	----------
	inputSourceModel : vtkMRMLModelNode
		A Glyph representation of the detected fiducials in the input volume.

	inputTargetModel : vtkMRMLModelNode
		A Glyph representation of the stereotactic frame system.
	
	icpTransform : vtkMRMLLinearTransformNode
		The linear transform from ICP registration.

	Returns
	-------
	sourceGlyphNode : vtkMRMLMModelNode
		A Glyph representation of the detected fiducials in the input volume.
	
	"""
	sourcePolyData = inputSourceModel.GetPolyData() if not isinstance(inputSourceModel,vtk.vtkAppendPolyData) else inputSourceModel.GetOutput()
	targetPolyData = inputTargetModel.GetPolyData() if not isinstance(inputTargetModel,vtk.vtkAppendPolyData) else inputTargetModel.GetOutput()

	cellId = vtk.mutable(0)
	subId = vtk.mutable(0)
	dist2 = vtk.mutable(0.0)
	cellLocator = vtk.vtkCellLocator()
	cellLocator.SetDataSet(targetPolyData)
	cellLocator.SetNumberOfCellsPerBucket(1)
	cellLocator.BuildLocator()
	
	accumDist = []
	accumPoints = []
	sourcePointsAccum = []
	idealPoints = []
	totalDistance = 0.0

	sourcePoints = sourcePolyData.GetPoints()
	n = sourcePoints.GetNumberOfPoints()
	m = vtk.vtkMath()
	for sourcePointIndex in range(n):
		sourcePointPos = np.zeros(3)
		sourcePoints.GetPoint(sourcePointIndex, sourcePointPos)
		transformedSourcePointPos = np.append(np.zeros(3),1)
		sourcePointPos=np.append(sourcePointPos,1)
		icpTransform.GetTransformToParent().MultiplyPoint(sourcePointPos, transformedSourcePointPos)
		surfacePoint = np.zeros(3)
		transformedSourcePointPos = transformedSourcePointPos[:3]
		#find the squared distance between the points
		cellLocator.FindClosestPoint(transformedSourcePointPos, surfacePoint, cellId, subId, dist2)
		# take the square root to get the Euclidean distance between the points
		sourcePointsAccum.append(transformedSourcePointPos)
		idealPoints.append(surfacePoint)
		accumPoints.append(np.array(transformedSourcePointPos)-np.array(surfacePoint))
		accumDist.append(math.sqrt(dist2))
		totalDistance = totalDistance + accumDist[-1]

	return (totalDistance / n), accumDist, np.vstack(accumPoints), np.vstack(sourcePointsAccum), np.vstack(idealPoints)
 
def runFrameModelRegistration(inputSourceModel, inputTargetModel, inputTransform, transformType, numIterations, numLandmarks, 
	matchCentroids, sourceRadius=None,distanceMetric='rms',maximum_mean_distance=0.001,check_mean_distance=True):
	"""Runs iterative closest point registration.

	Parameters
	----------
	inputSourceModel : vtkMRMLModelNode
		A Glyph representation of the detected fiducials in the input volume.

	inputTargetModel : vtkMRMLModelNode
		A Glyph representation of the stereotactic frame system.

	inputTransform : vtkMRMLLinearTransformNode
		The linear transform node to be updated from ICP registration matrix.

	transformType : int
		0 :
			Rigidbody - rotation and translation only.
		1 :
			Similarity - rotation, translation and isotropic scaling.
		2 :
			Affine - collinearity is preserved, ratios of distances along a line are preserved.

	Returns
	-------
	
	inputTransform : vtkMRMLLinearTransformNode
		The linear transform node updated from ICP registration matrix.
	
	"""
	icpTransform = vtk.vtkIterativeClosestPointTransform()

	if isinstance(inputTargetModel,vtk.vtkAppendPolyData):
		icpTransform.SetTarget(inputTargetModel.GetOutput())
	else:
		icpTransform.SetTarget(inputTargetModel.GetPolyData())
	if isinstance(inputSourceModel,vtk.vtkAppendPolyData):
		icpTransform.SetSource(inputSourceModel.GetOutput())
	else:
		icpTransform.SetSource(inputSourceModel.GetPolyData())
	
	#### set the maximum allowed distance
	icpTransform.SetMaximumMeanDistance(maximum_mean_distance)

	#### check the mean distance during registration
	if check_mean_distance:
		icpTransform.CheckMeanDistanceOn()

	#### start by matching the source and target point centroids
	icpTransform.StartByMatchingCentroidsOff()
	if matchCentroids:
		icpTransform.StartByMatchingCentroidsOn()
	
	#### type of transform to run
	if transformType == 0:
		icpTransform.GetLandmarkTransform().SetModeToRigidBody()
	elif transformType == 1:
		icpTransform.GetLandmarkTransform().SetModeToSimilarity()
	elif transformType == 2:
		icpTransform.GetLandmarkTransform().SetModeToAffine()
	
	#### distance metric to use (default RMS)
	icpTransform.SetMeanDistanceModeToRMS()
	if distanceMetric == 'abs':
		icpTransform.SetMeanDistanceModeToAbsoluteValue()

	#### max number of iterations to perform
	icpTransform.SetMaximumNumberOfIterations(numIterations)

	#### max number of fiducial points to use
	icpTransform.SetMaximumNumberOfLandmarks(numLandmarks)

	#### run the ICP registration
	icpTransform.Modified()
	icpTransform.Update()
	
	transform_matrix = vtk.vtkMatrix4x4()
	transform_matrix.DeepCopy(icpTransform.GetMatrix())

	#### apply the transform matrix to the main transform node
	inputTransform.SetMatrixTransformToParent(transform_matrix)

	return inputTransform

def centerOfMass(poly):
	""" Return center of mass of polydata.

	"""
	centerOfMassFilter = vtkCenterOfMass()
	centerOfMassFilter.SetInputData(poly)
	centerOfMassFilter.SetUseScalarsAsWeights(False)
	centerOfMassFilter.Update()

	return centerOfMassFilter.GetCenter()
	
def getFrameCenter(frame_system):
	"""Return the frame center as Markups node.

	Parameters
	----------
	frame_system : str
		The name of the stereotactic frame system.

	Returns
	-------
	FC : vtkMRMLMarkupsFiducialNode
		A Markups list containing the frame center coordinates along with
		the diagonal bar centers.
	
	"""
	transformNodeCT = None
	frameTopBot = None

	if len(slicer.util.getNodes('*from-*Frame_to*')) > 0:
		transformNodeCT = list(slicer.util.getNodes('*from-*Frame_to*').values())[0]
	
	if len(slicer.util.getNodes('*topbottom_fids*')) > 0:
		frameTopBot = list(slicer.util.getNodes('*topbottom_fids*').values())[0]

	if transformNodeCT is not None or frameTopBot is not None:
		fidNode = getMarkupsNode('frame_center', node_type='vtkMRMLMarkupsFiducialNode', create=False)
		if fidNode is None:
			a_top = np.zeros(3)
			c_bot = np.zeros(3)
			d_top = np.zeros(3)
			f_bot = np.zeros(3)
			g_bot = np.zeros(3)
			i_top = np.zeros(3)

			for ifid in range(frameTopBot.GetNumberOfControlPoints()):
				if 'A_top' in frameTopBot.GetNthControlPointLabel(ifid):
					frameTopBot.GetNthControlPointPositionWorld(ifid, a_top)
				elif 'C_bot' in frameTopBot.GetNthControlPointLabel(ifid):
					frameTopBot.GetNthControlPointPositionWorld(ifid, c_bot)
				elif 'D_top' in frameTopBot.GetNthControlPointLabel(ifid):
					frameTopBot.GetNthControlPointPositionWorld(ifid, d_top)
				elif 'F_bot' in frameTopBot.GetNthControlPointLabel(ifid):
					frameTopBot.GetNthControlPointPositionWorld(ifid, f_bot)
				elif 'G_bot' in frameTopBot.GetNthControlPointLabel(ifid):
					frameTopBot.GetNthControlPointPositionWorld(ifid, g_bot)
				elif 'I_top' in frameTopBot.GetNthControlPointLabel(ifid):
					frameTopBot.GetNthControlPointPositionWorld(ifid, i_top)

			midB = np.array(a_top) + norm_vec(a_top, c_bot) * ((mag_vec(a_top, c_bot) / 2))
			midE = np.array(d_top) + norm_vec(d_top, f_bot) * ((mag_vec(d_top, f_bot) / 2))
			midH = np.array(i_top) + norm_vec(i_top, g_bot) * ((mag_vec(i_top, g_bot) / 2))

			if any(x in frame_system for x in ('leksell','crw')):
				FC = np.array([(midB[0] + midH[0]) / 2, (midB[1] + midH[1]) / 2, (midB[2] + midH[2]) / 2])
			elif 'brw' in frame_system:
				FC = np.array([(midB[0] + midE[0] + midH[0]) / 3, (midB[1] + midE[1] + midH[1]) / 3, (midB[2] + midE[2] + midH[2]) / 3])

			frameCentNode = getMarkupsNode('frame_center', node_type='vtkMRMLMarkupsFiducialNode', create=True)
			n = frameCentNode.AddControlPointWorld(vtk.vtkVector3d(FC[0], FC[1], FC[2]))
			frameCentNode.SetNthControlPointLabel(n, 'frame_center')
			frameCentNode.SetNthControlPointLocked(n, True)
			n = frameCentNode.AddControlPointWorld(vtk.vtkVector3d(midB[0], midB[1], midB[2]))
			frameCentNode.SetNthControlPointLabel(n, 'midB')
			frameCentNode.SetNthControlPointLocked(n, True)
			n = frameCentNode.AddControlPointWorld(vtk.vtkVector3d(midE[0], midE[1], midE[2]))
			frameCentNode.SetNthControlPointLabel(n, 'midE')
			frameCentNode.SetNthControlPointLocked(n, True)
			n = frameCentNode.AddControlPointWorld(vtk.vtkVector3d(midH[0], midH[1], midH[2]))
			frameCentNode.SetNthControlPointLabel(n, 'midH')
			frameCentNode.SetNthControlPointLocked(n, True)

			frameCentNode.GetDisplayNode().VisibilityOff()
		else:
			FC = getPointCoords('frame_center', 'frame_center', node_type='vtkMRMLMarkupsFiducialNode')

	return FC

def adjustPrecision(vector, num_precision=3):
	"""Controls precision of input values.
	
	Parameters
	----------
	vector : ndarray or float
		The values to round.

	num_precision : int, default 3
		The precision to use while rounding.

	Returns
	-------
	out : ndarray
		The values rounded to the requested precision.

	"""
	if isinstance(vector, float):
		out = np.round(vector, num_precision)
	else:
		out = np.array(np.round(vector, num_precision))
	return out

def get_model_point(node):
	"""Gets model point positions for supplied model node.
	
	Parameters
	----------
	node : vtkMRMLModelNode
		The model node to obtain points from.

	Returns
	-------
	point_Ras : ndarray
		The model point as a numpy array.

	"""
	a = slicer.util.arrayFromModelPoints(node)
	np.append(a[ipoint], 1.0)
	point_Ras = []
	for ipoint in range(len(a)):
		volumeIjkToRas = vtk.vtkMatrix4x4()
		point_VolumeRas = np.append(np.zeros(3),1)
		sourcePoint=np.append(a[ipoint], 1)
		volumeIjkToRas.MultiplyPoint(sourcePoint, point_VolumeRas)
		transformVolumeRasToRas = vtk.vtkGeneralTransform()
		slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(node.GetParentTransformNode(), None, transformVolumeRasToRas)
		point_Ras.append(transformVolumeRasToRas.TransformPoint(point_VolumeRas[0:3]))

	return np.array(point_Ras[:3])

def getPointCoords(node_name, point_name, remove=False, node_type='vtkMRMLMarkupsFiducialNode', world=True):
	"""Return fiducial coordinates from node if point exists.
	
	Parameters
	----------
	node_name : str
		The node name to query.

	point_name : str
		The fiducial point name to obtain.

	remove : bool, default False
		Whether to remove all control points from the node.

	node_type : str, default 'vtkMRMLMarkupsFiducialNode'
		The type of node to search the scene for.
	
	world : bool, default True
		Whether to return the local or global coordinates
	
	Returns
	-------
	point_coord : ndarray
		If the point exists in the node it's coordinates are returned,
		else an array of zeros is returned.
	
	"""
	models = slicer.util.getNodesByClass(node_type)
	final_coord = []
	for i in models:
		if node_name == i.GetName():
			for ifid in range(i.GetNumberOfControlPoints()):
				if point_name in i.GetNthControlPointLabel(ifid):
					point_coord = np.zeros(3)
					if world:
						i.GetNthControlPointPositionWorld(ifid, point_coord)
					else:
						i.GetNthControlPointPosition(ifid, point_coord)
					final_coord = point_coord.copy()
			if len(final_coord)>0 and remove and sum(point_coord) > 0:
				i.RemoveAllControlPoints()
	if not len(final_coord)>0:
		final_coord = [float(0.0)]*3
	return np.array(final_coord[0:3])

def getMarkupsNode(node_name, node_type='vtkMRMLMarkupsFiducialNode', create=False):
	"""Obtains/creates desired node in scene.

	Parameters
	----------
	node_name : str
		The name of the desired node.

	node_type : str, default 'vtkMRMLMarkupsFiducialNode'
		The type of node desired.
	
	create : bool
		Whether to create the node if ti doesn't already exists in the scene.

	Returns
	-------
	NormVec : ndarray
		The normal vector of the vector.
	
	"""
	nodes = slicer.util.getNodesByClass(node_type)
	markupsNode = None
	for inode in nodes:
		if inode.GetName() == node_name:
			markupsNode = inode

	if markupsNode is None:
		if create:
			markupsNode = slicer.mrmlScene.AddNewNodeByClass(node_type)
			markupsNode.SetName(node_name)
			markupsNode.AddDefaultStorageNode()
			markupsNode.GetStorageNode().SetCoordinateSystem(coordSys)
	
	return markupsNode

def applyTransformToPoints(transform, points, reverse=False):
	transformMatrix = vtk.vtkGeneralTransform()
	if reverse:
		slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(None, transform, transformMatrix)
	else:
		slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(transform, None, transformMatrix)
	finalPoints = transformMatrix.TransformPoint(points)
	return np.array(finalPoints)

def frame_angles(Xt, Xe):
	if not isinstance(Xt,np.ndarray):
		Xt = np.array(Xt)
	if not isinstance(Xe,np.ndarray):
		Xe = np.array(Xe)
	Xr = np.array(Xe - Xt)
	dist = np.linalg.norm(Xr)
	phi = np.array([0.0, 0.0])
	phi[0] = np.arccos(Xr[0] / dist)
	if Xr[1] != 0:
		phi[1] = np.arctan(Xr[2] / Xr[1])
	else:
		phi[1] = np.pi / 2.0
	if phi[1] < 0:
		phi[1] = np.pi + phi[1]
	return math.degrees(phi[0]), math.degrees(phi[1])

def getFrameRotation():

	if len(slicer.util.getNodes('*frame_rotation*')) == 0:
		ac = getPointCoords('acpc', 'ac', world=True)
		pc = getPointCoords('acpc', 'pc', world=True)
		mid = getPointCoords('midline', 'mid1', world=True)

		#frameTransform=list(slicer.util.getNodes('*desc-rigid_from-*Frame*').values())[0]
		#ac=applyTransformToPoints(frameTransform,ac,True)
		#pc=applyTransformToPoints(frameTransform,pc,True)
		#mid=applyTransformToPoints(frameTransform,mid,True)

		pmprime = (ac + pc) / 2
		vec1 = ac - pmprime
		vec2 = mid - pmprime
		vec1Mag = np.sqrt(vec1[0] ** 2 + vec1[1] ** 2 + vec1[2] ** 2)
		vec2Mag = np.sqrt(vec2[0] ** 2 + vec2[1] ** 2 + vec2[2] ** 2)
		vec1Unit = vec1 / vec1Mag
		vec2Unit = vec2 / vec2Mag
		yihatprime = vec1Unit
		if pmprime[2] > mid[2]:
			xihatprime = np.cross(vec2Unit, vec1Unit)
		else:
			xihatprime = np.cross(vec1Unit, vec2Unit)
		xAxisMag = (xihatprime[0] ** 2 + xihatprime[1] ** 2 + xihatprime[2] ** 2) ** 0.5
		xihatprime = xihatprime / xAxisMag
		zAxis = np.cross(xihatprime, yihatprime)
		zAxisMag = (zAxis[0] ** 2 + zAxis[1] ** 2 + zAxis[2] ** 2) ** 0.5
		zihatprime = zAxis / zAxisMag
		xihat = np.array([1, 0, 0])
		yihat = np.array([0, 1, 0])
		zihat = np.array([0, 0, 1])
		riiprime = np.vstack([np.array([xihatprime.dot(xihat), xihatprime.dot(yihat), xihatprime.dot(zihat)]),
							 np.array([yihatprime.dot(xihat), yihatprime.dot(yihat), yihatprime.dot(zihat)]),
							 np.array([zihatprime.dot(xihat), zihatprime.dot(yihat), zihatprime.dot(zihat)])])

		frameRotation = slicer.mrmlScene.AddNode(slicer.vtkMRMLLinearTransformNode())
		frameRotation.SetName('frame_rotation')
		frameRotationMatrix = vtk.vtkMatrix4x4()
		frameRotationMatrix.SetElement(0, 0, riiprime[0][0])
		frameRotationMatrix.SetElement(0, 1, riiprime[0][1])
		frameRotationMatrix.SetElement(0, 2, riiprime[0][2])
		frameRotationMatrix.SetElement(1, 0, riiprime[1][0])
		frameRotationMatrix.SetElement(1, 1, riiprime[1][1])
		frameRotationMatrix.SetElement(1, 2, riiprime[1][2])
		frameRotationMatrix.SetElement(2, 0, riiprime[2][0])
		frameRotationMatrix.SetElement(2, 1, riiprime[2][1])
		frameRotationMatrix.SetElement(2, 2, riiprime[2][2])

		frameRotation.SetMatrixTransformToParent(frameRotationMatrix)
	else:
		frameRotation=slicer.util.getNode('frame_rotation')

	return frameRotation

def shMatrixRotFromTwoSystems(from0,from1,from2,to0,to1,to2,transformationMatrix):
	sys_matrix=vtk.vtkMatrix4x4()
	x1 = from1 - from0
	if len(x1)== 0.0:
		print("shMatrixRotFromTwoSystems: from1 - from0 == 0.0 return ERROR\n")
		return
	else:
		x1=x1/np.sqrt(np.sum(x1**2))
	y1 = from2 - from0
	if len(y1)== 0.0:
		print("shMatrixRotFromTwoSystems: from2 - from0 == 0.0 return ERROR\n")
		return
	else:
		y1=y1/np.sqrt(np.sum(y1**2))
	x2 = to1 - to0
	if len(x2)== 0.0:
		print("shMatrixRotFromTwoSystems: to1 - to0 == 0.0 return ERROR\n")
		return
	else:
		x2=x2/np.sqrt(np.sum(x2**2))
	y2 = to2 - to0
	if len(y2)== 0.0:
		print("shMatrixRotFromTwoSystems: to2 - to0 == 0.0 return ERROR\n")
		return
	else:
		y2=y2/np.sqrt(np.sum(y2**2))
	cos1 = x1 @ y1
	cos2 = x2 @ y2
	if (abs(1.0 - cos1) <= 0.000001) & (abs(1.0 - cos2) <= 0.000001):
		sys_matrix.SetElement(3, 0, to0[0] - from0[0])
		sys_matrix.SetElement(3, 1, to0[1] - from0[1])
		sys_matrix.SetElement(3, 2, to0[2] - from0[2])
		transformationMatrix.SetMatrixTransformToParent(sys_matrix)
	if abs(cos1 - cos2) > 0.08:
		sys_matrix.SetElement(3, 0, to0[0] - from0[0])
		sys_matrix.SetElement(3, 1, to0[1] - from0[1])
		sys_matrix.SetElement(3, 2, to0[2] - from0[2])
		transformationMatrix.SetMatrixTransformToParent(sys_matrix)
	z1 = np.cross(x1,y1)
	z1 = z1/np.sqrt(np.sum(z1**2))
	y1 = np.cross(z1,x1)
	z2 = np.cross(x2,y2)
	z2 = z2/np.sqrt(np.sum(z2**2))
	y2 = np.cross(z2,x2)
	detxx = (y1[1] * z1[2] - z1[1] * y1[2])
	detxy = -(y1[0] * z1[2] - z1[0] * y1[2])
	detxz = (y1[0] * z1[1] - z1[0] * y1[1])
	detyx = -(x1[1] * z1[2] - z1[1] * x1[2])
	detyy = (x1[0] * z1[2] - z1[0] * x1[2])
	detyz = -(x1[0] * z1[1] - z1[0] * x1[1])
	detzx = (x1[1] * y1[2] - y1[1] * x1[2])
	detzy = -(x1[0] * y1[2] - y1[0] * x1[2])
	detzz = (x1[0] * y1[1] - y1[0] * x1[1])
	txx = x2[0] * detxx + y2[0] * detyx + z2[0] * detzx
	txy = x2[0] * detxy + y2[0] * detyy + z2[0] * detzy
	txz = x2[0] * detxz + y2[0] * detyz + z2[0] * detzz
	tyx = x2[1] * detxx + y2[1] * detyx + z2[1] * detzx
	tyy = x2[1] * detxy + y2[1] * detyy + z2[1] * detzy
	tyz = x2[1] * detxz + y2[1] * detyz + z2[1] * detzz
	tzx = x2[2] * detxx + y2[2] * detyx + z2[2] * detzx
	tzy = x2[2] * detxy + y2[2] * detyy + z2[2] * detzy
	tzz = x2[2] * detxz + y2[2] * detyz + z2[2] * detzz
	# set transformation
	dx1 = from0[0]
	dy1 = from0[1]
	dz1 = from0[2]
	dx2 = to0[0]
	dy2 = to0[1]
	dz2 = to0[2]
	sys_matrix.SetElement(0, 0, txx)
	sys_matrix.SetElement(1, 0, txy)
	sys_matrix.SetElement(2, 0, txz)
	sys_matrix.SetElement(0, 1, tyx)
	sys_matrix.SetElement(1, 1, tyy)
	sys_matrix.SetElement(2, 1, tyz)
	sys_matrix.SetElement(0, 2, tzx)
	sys_matrix.SetElement(1, 2, tzy)
	sys_matrix.SetElement(2, 2, tzz)
	sys_matrix.SetElement(3, 0, dx2 - txx * dx1 - txy * dy1 - txz * dz1)
	sys_matrix.SetElement(3, 1, dy2 - tyx * dx1 - tyy * dy1 - tyz * dz1)
	sys_matrix.SetElement(3, 2, dz2 - tzx * dx1 - tzy * dy1 - tzz * dz1)
	transformationMatrix.SetMatrixTransformToParent(sys_matrix)
	return transformationMatrix

def getFrameRotation_new():

	if len(slicer.util.getNodes('*frame_rotation*')) == 0:

		acInternalCoords = getPointCoords('acpc', 'ac', world=True)
		pcInternalCoords = getPointCoords('acpc', 'pc', world=True)
		mpPointInternalCoords = getPointCoords('midline', 'mid1', world=True)

		frameRotation = slicer.vtkMRMLLinearTransformNode()
		frameRotation.SetName('frame_rotation')
		slicer.mrmlScene.AddNode(frameRotation)

		acPcMidPoint=np.array([0.0,0.0,0.0])
		internalAcToPcVec = acInternalCoords + (acInternalCoords - pcInternalCoords)
		internalMidPoint = (acInternalCoords + pcInternalCoords)/2
		acPcAcToPcVec =np.array([0.0,float(mag_vec(pcInternalCoords,acInternalCoords)),0.0])

		l = shLs([ acInternalCoords, pcInternalCoords])
		dist=shPt(mpPointInternalCoords).distance(l)

		internalAcPcClosestPointToMpp= np.array(l.interpolate(dist).coords[0])

		internalLinePerpendicular = mpPointInternalCoords- internalAcPcClosestPointToMpp
		internalMcpPerpendicular = internalMidPoint + internalLinePerpendicular
		acPcAcPerpendicular = np.array([0.0, 0.0, np.linalg.norm(internalLinePerpendicular)])

		M=shMatrixRotFromTwoSystems(
			internalMidPoint,
			internalAcToPcVec,
			internalMcpPerpendicular,
			acPcMidPoint,
			acPcAcToPcVec,
			acPcAcPerpendicular,
			frameRotation
		)

		matrixFromWorld = vtk.vtkMatrix4x4()
		frameRotation.GetMatrixTransformFromWorld(matrixFromWorld)
	else:
		frameRotation=slicer.util.getNode('frame_rotation')

	return frameRotation



def mag_vec(P1, P2):
	"""Creates a normal vector between two points.
	
	Parameters
	----------
	P1 : ndarray
		Start point coordinates.

	P2 : ndarray
		Endpoint coordinates.
	
	Returns
	-------
	MagVec : int
		The magnitude of the vector.

	"""
	if isinstance(P1, list):
		P1 = np.array(P1)
	if isinstance(P1, list):
		P2 = np.array(P2)
	DirVec = P2-P1
	MagVec = np.sqrt([np.square(DirVec[0]) + np.square(DirVec[1]) + np.square(DirVec[2])])
	return MagVec


def norm_vec(P1, P2):
	"""Creates a normal vector between two points.

	Parameters
	----------
	P1 : ndarray
		Start point coordinates.

	P2 : ndarray
		End point coordinates.
	
	Returns
	-------
	NormVec : ndarray
		The normal vector of the vector.

	"""
	if isinstance(P1, list):
		P1 = np.array(P1)

	if isinstance(P2, list):
		P2 = np.array(P2)

	DirVec = P2-P1
	MagVec = np.sqrt([np.square(DirVec[0]) + np.square(DirVec[1]) + np.square(DirVec[2])])
	NormVec = np.array([float(DirVec[0] / MagVec), float(DirVec[1] / MagVec), float(DirVec[2] / MagVec)])

	return NormVec

def rotateTrajectory(target,arcAngle,ringAngle,dist):
	RASToFrame = np.array([
		[ 1, 0, 0, 100],
		[ 0, 1, 0, 100],
		[ 0, 0,-1, 100],
		[ 0, 0, 0,   1]
	])
	x = np.cos(math.radians(arcAngle))*np.sin(math.radians(ringAngle))
	y = np.sin(math.radians(arcAngle))
	z = np.cos(math.radians(arcAngle))*np.cos(math.radians(ringAngle))
	new_point=target+np.array([x,y,z])*dist
	new_point=np.dot(RASToFrame, np.append(new_point,1))[:3]
	return new_point

def CT_to_frame_coords(TP, FC):
	frame_target_X = float(np.diff((TP[0], FC[0])))
	frame_target_Y = float(np.diff((TP[1], FC[1])))
	frame_target_Z = float(np.diff((TP[2], FC[2])))
	frame_target = []
	if frame_target_X < 0:
		frame_target.append(100 - abs(frame_target_X))
	else:
		frame_target.append(100 + abs(frame_target_X))
	if frame_target_Y > 0:
		frame_target.append(100 - abs(frame_target_Y))
	else:
		frame_target.append(100 + abs(frame_target_Y))
	if frame_target_Z < 0:
		frame_target.append(100 - abs(frame_target_Z))
	else:
		frame_target.append(100 + abs(frame_target_Z))
	return frame_target

def rotation_matrix(pitch, roll, yaw):
	"""Creates rotation matrix from Euler angles.

	Parameters
	----------
	P1: ndarray
		Starting point coordinates.

	P2 : ndarray
		Ending point coordinates.
	
	Returns
	-------
	NormVec : ndarray
		The normal vector of the vector.

	"""
	pitch, roll, yaw = np.array([pitch, roll, yaw]) * np.pi / 180
	matrix_pitch = np.array([
		[np.cos(pitch), 0, np.sin(pitch)],
		[0, 1, 0],
		[-np.sin(pitch), 0, np.cos(pitch)]
	])
	matrix_roll = np.array([
		[1, 0, 0],
		[0, np.cos(roll), -np.sin(roll)],
		[0, np.sin(roll), np.cos(roll)]
	])
	matrix_yaw = np.array([
		[np.cos(yaw), -np.sin(yaw), 0],
		[np.sin(yaw), np.cos(yaw), 0],
		[0, 0, 1]
	])
	return np.dot(matrix_pitch, np.dot(matrix_roll, matrix_yaw))

#curveNode=np.vstack([centerOfMass['P1'],centerOfMass['P3'],centerOfMass['P7'],centerOfMass['P9']])

#https://github.com/PerkLab/SlicerSandbox/blob/master/CurvedPlanarReformat/CurvedPlanarReformat.py
def computeStraighteningTransform(transformToStraightenedNode, curveNode, sliceSizeMm, outputSpacingMm):
	"""
	Compute straightened volume (useful for example for visualization of curved vessels)
	resamplingCurveSpacingFactor: 
	"""
	transformSpacingFactor = 5.0
	# Create a temporary resampled curve
	resamplingCurveSpacing = outputSpacingMm * transformSpacingFactor
	originalCurvePoints = curveNode.GetCurvePointsWorld()
	sampledPoints = vtk.vtkPoints()
	if not slicer.vtkMRMLMarkupsCurveNode.ResamplePoints(originalCurvePoints, sampledPoints, resamplingCurveSpacing, False):
		raise("Redampling curve failed")
	resampledCurveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", "CurvedPlanarReformat_resampled_curve_temp")
	resampledCurveNode.SetNumberOfPointsPerInterpolatingSegment(1)
	resampledCurveNode.SetCurveTypeToLinear()
	resampledCurveNode.SetControlPointPositionsWorld(sampledPoints)
	numberOfSlices = resampledCurveNode.GetNumberOfControlPoints()

	# Z axis (from first curve point to last, this will be the straightened curve long axis)
	curveStartPoint = np.zeros(3)
	curveEndPoint = np.zeros(3)
	resampledCurveNode.GetNthControlPointPositionWorld(0, curveStartPoint)
	resampledCurveNode.GetNthControlPointPositionWorld(resampledCurveNode.GetNumberOfControlPoints()-1, curveEndPoint)
	transformGridAxisZ = (curveEndPoint-curveStartPoint)/np.linalg.norm(curveEndPoint-curveStartPoint)

	# X axis = average X axis of curve, to minimize torsion (and so have a simple displacement field, which can be robustly inverted)
	sumCurveAxisX_RAS = np.zeros(3)
	for gridK in range(len(curveNode)):
		curveAxisX_RAS = curveNode[gridK]
		sumCurveAxisX_RAS += curveAxisX_RAS

	meanCurveAxisX_RAS = sumCurveAxisX_RAS/np.linalg.norm(sumCurveAxisX_RAS)
	transformGridAxisX = meanCurveAxisX_RAS

	# Y axis
	transformGridAxisY = np.cross(transformGridAxisZ, transformGridAxisX)
	transformGridAxisY = transformGridAxisY/np.linalg.norm(transformGridAxisY)

	# Make sure that X axis is orthogonal to Y and Z
	transformGridAxisX = np.cross(transformGridAxisY, transformGridAxisZ)
	transformGridAxisX = transformGridAxisX/np.linalg.norm(transformGridAxisX)

	# Origin (makes the grid centered at the curve)
	curveLength = resampledCurveNode.GetCurveLengthWorld()
	curveNodePlane = vtk.vtkPlane()
	slicer.modules.markups.logic().GetBestFitPlane(resampledCurveNode, curveNodePlane)
	transformGridOrigin = np.array(curveNodePlane.GetOrigin())
	transformGridOrigin -= transformGridAxisX * sliceSizeMm[0]/2.0
	transformGridOrigin -= transformGridAxisY * sliceSizeMm[1]/2.0
	transformGridOrigin -= transformGridAxisZ * curveLength/2.0

	# Create grid transform
	# Each corner of each slice is mapped from the original volume's reformatted slice
	# to the straightened volume slice.
	# The grid transform contains one vector at the corner of each slice.
	# The transform is in the same space and orientation as the straightened volume.

	gridDimensions = [2, 2, numberOfSlices]
	gridSpacing = [sliceSizeMm[0], sliceSizeMm[1], resamplingCurveSpacing]
	gridDirectionMatrixArray = np.eye(4)
	gridDirectionMatrixArray[0:3, 0] = transformGridAxisX
	gridDirectionMatrixArray[0:3, 1] = transformGridAxisY
	gridDirectionMatrixArray[0:3, 2] = transformGridAxisZ
	gridDirectionMatrix = slicer.util.vtkMatrixFromArray(gridDirectionMatrixArray)

	gridImage = vtk.vtkImageData()
	gridImage.SetOrigin(transformGridOrigin)
	gridImage.SetDimensions(gridDimensions)
	gridImage.SetSpacing(gridSpacing)
	gridImage.AllocateScalars(vtk.VTK_DOUBLE, 3)
	transform = slicer.vtkOrientedGridTransform()
	transform.SetDisplacementGridData(gridImage)
	transform.SetGridDirectionMatrix(gridDirectionMatrix)
	transformToStraightenedNode.SetAndObserveTransformFromParent(transform)

	# Compute displacements
	transformDisplacements_RAS = slicer.util.arrayFromGridTransform(transformToStraightenedNode)
	for gridK in range(gridDimensions[2]):
		curvePointToWorld = vtk.vtkMatrix4x4()
		resampledCurveNode.GetCurvePointToWorldTransformAtPointIndex(resampledCurveNode.GetCurvePointIndexFromControlPointIndex(gridK), curvePointToWorld)
		curvePointToWorldArray = slicer.util.arrayFromVTKMatrix(curvePointToWorld)
		curveAxisX_RAS = curvePointToWorldArray[0:3, 0]
		curveAxisY_RAS = curvePointToWorldArray[0:3, 1]
		curvePoint_RAS = curvePointToWorldArray[0:3, 3]
		for gridJ in range(gridDimensions[1]):
			for gridI in range(gridDimensions[0]):
				straightenedVolume_RAS = (transformGridOrigin
					+ gridI*gridSpacing[0]*transformGridAxisX
					+ gridJ*gridSpacing[1]*transformGridAxisY
					+ gridK*gridSpacing[2]*transformGridAxisZ)
				inputVolume_RAS = (curvePoint_RAS
					+ (gridI-0.5)*sliceSizeMm[0]*curveAxisX_RAS
					+ (gridJ-0.5)*sliceSizeMm[1]*curveAxisY_RAS)
				transformDisplacements_RAS[gridK][gridJ][gridI] = inputVolume_RAS - straightenedVolume_RAS
	slicer.util.arrayFromGridTransformModified(transformToStraightenedNode)

	slicer.mrmlScene.RemoveNode(resampledCurveNode)  # delete temporary curve


def plotLead(entry,target,origin,model_parameters):
	"""Creates a vtk model of electrode.
	
	Parameters
	----------
	entry : ndarray
		The entry point coordinates.

	target : ndarray
		The target point coordinates.

	origin : ndarray
		The origin point used to reference the entry/target points.
	
	model_parameters : dict
	
	Returns
	-------
	NormVec : ndarray
		The normal vector of the vector.
	
	"""

	if isinstance(model_parameters['model_col'],str):
		model_parameters['model_col'] = hex2rgb(model_parameters['model_col'])

	entry_origin = entry - origin.copy()
	target_origin = target - origin.copy()
	
	NormVec = norm_vec(target,entry)
	
	coordsFile = []
	coordsFile.append([model_parameters['plan_name'], model_parameters['type'], 'entry', entry_origin[0], entry_origin[1], entry_origin[2]])
	coordsFile.append([model_parameters['plan_name'], model_parameters['type'], 'target', target_origin[0], target_origin[1], target_origin[2]])

	csvfile = os.path.join(model_parameters['data_dir'], 'summaries', 'lead_coordinates.csv')
	if not os.path.exists(csvfile):
		header=['plan_name', 'type', 'point', 'X', 'Y', 'Z']
		with open(csvfile, 'w') as (output):
			writer = csv.writer(output, lineterminator='\n')
			writer.writerows(header)

	with open(csvfile, 'a') as (output):
		writer = csv.writer(output, lineterminator='\n')
		writer.writerows(coordsFile)

	#### remove any pre-existing vtk models of the same name
	nodes = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
	for inodes in nodes:
		if os.path.split(model_parameters['lead_fileN'])[(-1)].split('type-')[0] in inodes.GetName() and '_lead' in inodes.GetName():
			filepath = slicer.util.getNode(inodes.GetID()).GetStorageNode().GetFileName()
			slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))
			os.remove(filepath)


	electrode_index = [i for i, x in enumerate(electrodeModels.keys()) if model_parameters['elecUsed'].lower() == x.lower()][0]
	e_specs = electrodeModels[list(electrodeModels)[electrode_index]]


	vtkModelBuilder = vtkModelBuilderClass()
	vtkModelBuilder.coords = np.hstack((np.array(target), np.array(entry)))
	vtkModelBuilder.tube_radius = e_specs['diameter']
	vtkModelBuilder.tube_thickness = 0.2
	vtkModelBuilder.filename = os.path.join(model_parameters['data_dir'], model_parameters['lead_fileN'])
	vtkModelBuilder.model_color = model_parameters['model_col']
	vtkModelBuilder.model_visibility = model_parameters['model_vis']
	vtkModelBuilder.build_electrode()
	if model_parameters['plot_model']:
		vtkModelBuilder.add_to_scene()

	
	#### this will be updated within the loop so need to assign to variable.
	start = e_specs['encapsultation']
	contact_diameter = e_specs['diameter']+.01

	#### build each contact in the electrode
	bottomTop = np.empty([0, 6])
	contactFile = []
	for iContact in range(0, e_specs['num_groups']):
		bottomTop = np.append(bottomTop, (np.hstack((
			np.array([[target[0] + NormVec[0] * start], 
				[target[1] + NormVec[1] * start], 
				[target[2] + NormVec[2] * start]]
			).T,
			np.array([[target[0] + NormVec[0] * (start + e_specs['contact_size'])], 
				[target[1] + NormVec[1] * (start + e_specs['contact_size'])], 
				[target[2] + NormVec[2] * (start + e_specs['contact_size'])]]
			).T))), axis=0)
		
		filen = os.path.join(model_parameters['data_dir'], model_parameters['contact_fileN'] % (str(iContact + 1).zfill(2)))

		nodes = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
		for inodes in nodes:
			if os.path.split(model_parameters['contact_fileN'])[(-1)].split('.vtk')[0] in inodes.GetName():
				filepath = slicer.util.getNode(inodes.GetID()).GetStorageNode().GetFileName()
				slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))
				os.remove(filepath)

		midContact = bottomTop[iContact, :3] + (bottomTop[iContact, 3:] - bottomTop[iContact, :3]) / 2
		contactFile.append([model_parameters['plan_name'], model_parameters['type'], str(iContact + 1), midContact[0] * -1, midContact[1] * -1, midContact[2]])
		if any(x.lower() in model_parameters['elecUsed'].lower() for x in ('directional', 'bsci_directional','b.sci. directional')):
			if iContact == 0:
				vtkModelBuilder = vtkModelBuilderClass()
				vtkModelBuilder.coords = bottomTop[iContact, :]
				vtkModelBuilder.tube_radius = contact_diameter
				vtkModelBuilder.tube_thickness = 0.3
				vtkModelBuilder.electrodeLen = e_specs['encapsultation']
				vtkModelBuilder.filename = filen
				vtkModelBuilder.model_color = model_parameters['contact_col']
				vtkModelBuilder.model_visibility = model_parameters['contact_vis']
				vtkModelBuilder.build_dir_bottomContact()
				if model_parameters['plot_model']:
					vtkModelBuilder.add_to_scene()
			
			elif iContact == 1 or iContact == 2:
				base_name = os.path.basename(filen)
				filen1 = os.path.join(model_parameters['data_dir'], '_'.join([base_name.split('_contact')[0], 'run-01', 'contact.vtk']))
				filen2 = os.path.join(model_parameters['data_dir'], '_'.join([base_name.split('_contact')[0], 'run-02', 'contact.vtk']))
				filen3 = os.path.join(model_parameters['data_dir'], '_'.join([base_name.split('_contact')[0], 'run-03', 'contact.vtk']))
				
				plane = np.vstack((
					[0.7, 1.0, 0.0],
					[1.0, -0.4, 0.0],
					[1.0, -0.4, 0.0]
				))

				nodes = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
				for inodes in nodes:
					if os.path.split(os.path.basename(filen1))[(-1)].split('.vtk')[0] in inodes.GetName():
						filepath = slicer.util.getNode(inodes.GetID()).GetStorageNode().GetFileName()				
						slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))
						os.remove(filepath)

				vtkModelBuilder = vtkModelBuilderClass()
				vtkModelBuilder.coords = bottomTop[iContact, :]
				vtkModelBuilder.tube_radius = contact_diameter
				vtkModelBuilder.tube_thickness = 0.3
				vtkModelBuilder.plane = plane
				vtkModelBuilder.filename = filen1
				vtkModelBuilder.model_color = model_parameters['contact_col']
				vtkModelBuilder.model_visibility = model_parameters['contact_vis']
				vtkModelBuilder.build_seg_contact()
				
				if model_parameters['plot_model']:
					vtkModelBuilder.add_to_scene()
				
				plane = np.vstack((
					[-1.0, -0.7, 0.0],
					[0.4, -1.0, 0.0],
					[0.4, -1.0, 0.0]
				))

				nodes = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
				for inodes in nodes:
					if os.path.split(os.path.basename(filen2))[(-1)].split('.vtk')[0] in inodes.GetName():
						filepath = slicer.util.getNode(inodes.GetID()).GetStorageNode().GetFileName()				
						slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))
						os.remove(filepath)

				vtkModelBuilder = vtkModelBuilderClass()
				vtkModelBuilder.coords = bottomTop[iContact, :]
				vtkModelBuilder.tube_radius = contact_diameter
				vtkModelBuilder.tube_thickness = 0.3
				vtkModelBuilder.plane = plane
				vtkModelBuilder.filename = filen2
				vtkModelBuilder.model_color = model_parameters['contact_col']
				vtkModelBuilder.model_visibility = model_parameters['contact_vis']
				vtkModelBuilder.build_seg_contact()
				if model_parameters['plot_model']:
					vtkModelBuilder.add_to_scene()
				
				plane = np.vstack((
					[-0.1, 1.0, 0.0],
					[-1.0, 0.1, 0.0],
					[-1.0, 0.1, 0.0]
				))

				nodes = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
				for inodes in nodes:
					if os.path.split(os.path.basename(filen3))[(-1)].split('.vtk')[0] in inodes.GetName():
						filepath = slicer.util.getNode(inodes.GetID()).GetStorageNode().GetFileName()				
						slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))
						os.remove(filepath)

				vtkModelBuilder = vtkModelBuilderClass()
				vtkModelBuilder.coords = bottomTop[iContact, :]
				vtkModelBuilder.tube_radius = contact_diameter
				vtkModelBuilder.tube_thickness = 0.3
				vtkModelBuilder.plane = plane
				vtkModelBuilder.filename = filen3
				vtkModelBuilder.model_color = model_parameters['contact_col']
				vtkModelBuilder.model_visibility = model_parameters['contact_vis']
				vtkModelBuilder.build_seg_contact()
				
				if model_parameters['plot_model']:
					vtkModelBuilder.add_to_scene()
			else:
				vtkModelBuilder = vtkModelBuilderClass()
				vtkModelBuilder.coords = bottomTop[iContact, :]
				vtkModelBuilder.tube_radius = contact_diameter
				vtkModelBuilder.tube_thickness = 0.3
				vtkModelBuilder.filename = filen
				vtkModelBuilder.model_color = model_parameters['contact_col']
				vtkModelBuilder.model_visibility = model_parameters['contact_vis']
				vtkModelBuilder.build_line()
				
				if model_parameters['plot_model']:
					vtkModelBuilder.add_to_scene()
		else:
			vtkModelBuilder = vtkModelBuilderClass()
			vtkModelBuilder.coords = bottomTop[iContact, :]
			vtkModelBuilder.tube_radius = contact_diameter
			vtkModelBuilder.tube_thickness = 0.3
			vtkModelBuilder.filename = filen
			vtkModelBuilder.model_color = model_parameters['contact_col']
			vtkModelBuilder.model_visibility = model_parameters['contact_vis']
			vtkModelBuilder.build_line()
		
			if model_parameters['plot_model']:
				vtkModelBuilder.add_to_scene()
		
		start += e_specs['contact_size']
		start += e_specs['contact_spacing']

	csvfile = os.path.join(model_parameters['data_dir'], 'summaries', 'contact_coordinates.csv')
	
	if not os.path.exists(csvfile):
		contactFileHeader = ['plan', 'type', 'contact', 'X', 'Y', 'Z']
		with open(csvfile, 'w') as (output):
			writer = csv.writer(output, lineterminator='\n')
			writer.writerows(contactFileHeader)
	
	with open(csvfile, 'a') as (output):
		writer = csv.writer(output, lineterminator='\n')
		writer.writerows(contactFile)


def plotMicroelectrode(coords, alpha, beta, model_parameters):
	"""Creates a vtk model of electrode.
	
	Parameters
	----------
	entry : ndarray
		The entry point coordinates.

	target : ndarray
		The target point coordinates.

	origin : ndarray
		The origin point used to reference the entry/target points.
	
	model_parameters : dict
	
	Returns
	-------
	NormVec : ndarray
		The normal vector of the vector.
	
	"""

	if isinstance(model_parameters['model_col'],str):
		model_parameters['model_col'] = hex2rgb(model_parameters['model_col'])

	#### remove any pre-existing vtk models of the same name
	nodes = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
	for inodes in nodes:
		if os.path.basename(model_parameters['mer_filename']) in inodes.GetName():
			filepath = slicer.util.getNode(inodes.GetID()).GetStorageNode().GetFileName()				
			slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))
			os.remove(filepath)

	node = slicer.util.loadModel(os.path.join(os.path.join(os.path.dirname(cwd), 'resources', 'models', microelectrodeModels['probes'][model_parameters['microUsed']])))
	node.SetName(os.path.basename(model_parameters['mer_filename']))
	node.GetModelDisplayNode().SetColor(model_parameters['model_col'])
	node.GetModelDisplayNode().SetSelectedColor(model_parameters['model_col'])
	node.GetDisplayNode().SetSliceIntersectionThickness(1)
	node.GetModelDisplayNode().SetSliceIntersectionVisibility(1)

	rotAng = 0
	if 'label-center' in os.path.basename(model_parameters['mer_filename']):
		rotAng = -45
	elif 'label-anterior' in os.path.basename(model_parameters['mer_filename']):
		rotAng = -180
	elif 'label-medial' in os.path.basename(model_parameters['mer_filename']):
		rotAng = -90
		if 'left' in model_parameters['side']:
			rotAng = 90
	elif 'label-lateral' in os.path.basename(model_parameters['mer_filename']):
		rotAng = 90
		if 'left' in model_parameters['side']:
			rotAng = -90
				
	sys_matrix=vtk.vtkTransform()
	sys_matrix.Translate(coords[:3])
	sys_matrix.RotateX(beta)
	sys_matrix.RotateY(alpha)
	sys_matrix.RotateZ(rotAng)

	sys_matrix2 = slicer.vtkMRMLLinearTransformNode()
	slicer.mrmlScene.AddNode(sys_matrix2)
	sys_matrix2.SetMatrixTransformToParent(sys_matrix.GetMatrix())

	node.SetAndObserveTransformNodeID(sys_matrix2.GetID())
	slicer.vtkSlicerTransformLogic.hardenTransform(node)
	slicer.mrmlScene.RemoveNode(sys_matrix2)

	slicer.util.saveNode(node, model_parameters['mer_filename'] + '.stl')


class VTAModelBuilderClass:

	def __init__(self, elspec, vatsettings=None):
		"""
				
		"""
		self.final_model = None
		self.elspec = elspec
		self.coords = elspec['coords']
		self.vatsettings = vatsettings
		self.nodeName = None if 'nodeName' not in list(self.elspec) else self.elspec['nodeName']
		self.filename = None if 'output_name' not in list(self.elspec) else self.elspec['output_name']
		self.main()

	def main(self):
		cnts = list(self.elspec['contact_info'].keys())
		
		if 'right' in self.elspec['side']:
			sidec = 'R'
		elif 'left' in self.elspec['side']:
			sidec = 'L'

		xx, yy, zz, _ = self.psphere(1000)

		index = [i for i, x in enumerate(electrodeModels.keys()) if self.elspec['elecUsed'].lower() == x.lower()][0]
		e_specs = electrodeModels[list(electrodeModels)[index]]
		
		S = {}
		S[sidec + 's0'] = self.elspec['contact_info']
		stimulation = []
		for key, val in self.elspec['contact_info'].items():
			if val['perc'] > 0:
				stimulation.append(key)
		
		radius = np.kron(np.ones((e_specs['num_groups'], 1)), e_specs['contact_size'])
		sources = [int(x) for x in np.linspace(0, len(S) - 1, len(S))]
		volume = np.zeros(len(radius))
		VAT = []
		K = []
		ivx = self.three_d_array(0, [len(sources), 3, 2])
		
		for source in sources:
			U = []
			Im = []
			stimsource = S[(sidec + 's' + str(source))]
			for cnt in range(len(cnts)):
				U.append(stimsource[cnts[cnt]]['perc'])
				Im.append(stimsource[cnts[cnt]]['imp'])

			Acnt = [x for i, x in enumerate(U) if x > 0]
			Aidx = [i for i, x in enumerate(U) if x > 0]
			if len(Acnt) > 1:
				print('In the Dembek model, only one active contact can be selected in each source')
			else:
				Im = Im[Aidx[0]]
				Im = Im
				U = stimsource[stimulation[0]]['amp']
				
				if self.elspec['VTA_algo'] == 'Dembek 17':
					if self.vatsettings == None:
						self.vatsettings = {}
						self.vatsettings['ethresh'] = 0.2
						self.vatsettings['ethresh_pw'] = 60
						self.vatsettings['pw'] = stimsource[stimulation[0]]['pw']
					radius[source] = self.dembek17_radius(U, Im, self.vatsettings['ethresh'], self.vatsettings['pw'], self.vatsettings['ethresh_pw'])
				elif self.elspec['VTA_algo'] == 'Kuncel':
					radius[source] = self.maedler12_eq3(U, Im)
				elif self.elspec['VTA_algo'] == 'Maedler 12':
					radius[source] = self.kuncel(U)
				
				volume[source] = 1.3333333333333333 * np.pi * radius[source] ** 3
				VAT.append(np.vstack((xx * radius[source] + self.coords[Aidx[0]][0],
					yy * radius[source] + self.coords[Aidx[0]][1],
					zz * radius[source] + self.coords[Aidx[0]][2])))
				
				CH = scipy.spatial.ConvexHull(VAT[source].T + np.random.rand(VAT[source].shape[1], VAT[source].shape[0]) * 1e-06)
				vid = np.sort(CH.vertices)
				mask = np.zeros((len(CH.points)), dtype=(np.int64))
				mask[vid] = np.arange(len(vid))
				K.append(mask[CH.simplices])
				for dim in range(3):
					ivx[source][dim][:] = [min(VAT[source][dim]), max(VAT[source][dim])]

				self.plotVTA(CH)

	def dembek17_radius(self, U, Im, ethresh, pw, ethresh_pw):
		r = 0
		if U:
			r = ((pw / ethresh_pw) ** 0.3) * np.sqrt((0.72 * (U / Im)) / (ethresh * 1000))
			r = r * 1000
			return r
		else:
			return

	def kuncel(self, U):
		"""
		This function radius of Volume of Activated Tissue for stimulation settings 
		U. See Kuncel 2008 for details. Clinical measurements of DBS electrode 
		impedance typically range from 500-1500 Ohm (Butson 2006).
		"""
		r = 0
		if U:
			k = 0.22
			Uo = 0.1
			r = np.sqrt((U - Uo) / k)
			return r
		else:
			return

	def maedler12_eq3(self, U, Im):
		"""
		This function radius of Volume of Activated Tissue for stimulation settings 
		U and Ohm. See Maedler 2012 for details. Clinical measurements of DBS 
		electrode impedance typically range from 500-1500 Ohm (Butson 2006).
		"""
		r = 0
		if U:
			k1 = -1.0473
			k3 = 0.2786
			k4 = 0.0009856
			r = -(k4 * Im - np.sqrt(k4 ** 2 * Im ** 2 + 2 * k1 * k4 * Im + k1 ** 2 + 4 * k3 * U) + k1) / (2 * k3)
			return r
		else:
			return

	def psphere(self, n):
		"""Distributes n points "equally" about a unit sphere.
		
		Parameters
		----------
		n : int
			The number of points to distribute.
		
		Returns
		-------
		x,y,z : 2D vector 
			Each is 1 x N vector
		r : float
			The smallest linear distance between two neighboring points. If the 
			function is run several times for the same n, r should not change 
			by more than the convergence criteria, which is +-0.01 on a unit 
			sphere.

		"""
		x = np.random.uniform(0, 1, n) - 0.5
		y = np.random.uniform(0, 1, n) - 0.5
		z = np.random.uniform(0, 1, n) - 0.5
		rm_new = np.ones((n, n))
		rm_old = np.zeros((n, n))
		r = np.sqrt(x ** 2 + y ** 2 + z ** 2)
		x = np.divide(x, r)
		y = np.divide(y, r)
		z = np.divide(z, r)
		not_done = True
		s = 1
		np.seterr(divide='ignore', invalid='ignore')
		while not_done:
			for i in range(n):
				ii = x[i] - x
				jj = y[i] - y
				kk = z[i] - z
				rm_new[i, :] = np.sqrt(ii ** 2 + jj ** 2 + kk ** 2)
				ii = np.divide(ii, rm_new[i, :])
				jj = np.divide(jj, rm_new[i, :])
				kk = np.divide(kk, rm_new[i, :])
				ii[i] = 0
				jj[i] = 0
				kk[i] = 0
				f = np.divide(1, 0.01 + rm_new[i, :] ** 2)
				fi = sum(np.multiply(f, ii))
				fj = sum(np.multiply(f, jj))
				fk = sum(np.multiply(f, kk))
				fn = np.sqrt(fi ** 2 + fj ** 2 + fk ** 2)
				fi = fi / fn
				fj = fj / fn
				fk = fk / fn
				x[i] = x[i] + np.multiply(s, fi)
				y[i] = y[i] + np.multiply(s, fj)
				z[i] = z[i] + np.multiply(s, fk)
				r = np.sqrt(x[i] ** 2 + y[i] ** 2 + z[i] ** 2)
				x[i] = x[i] / r
				y[i] = y[i] / r
				z[i] = z[i] / r

			diff = abs(rm_new - rm_old)
			not_done = diff.any() > 0.01
			rm_old = rm_new

		tmp = rm_new[:]
		avgr = min(tmp[(tmp != 0)])
		return (
		 x, y, z, avgr)

	def three_d_array(self, value, dim):
		"""
		Create 3D-array
		:param dim: a tuple of dimensions - (x, y, z)
		:param value: value with which 3D-array is to be filled
		:return: 3D-array
		"""
		return [[[value for _ in range(dim[2])] for _ in range(dim[1])] for _ in range(dim[0])]

	def plotVTA(self, CH):
		nodes = [x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if not slicer.vtkMRMLSliceLogic.IsSliceModelNode(x)]
		for inodes in nodes:
			if self.filename is not None:
				if self.elspec['output_name'].split('.vtk')[0] in inodes.GetName():
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))
			elif self.nodeName is not None:
				if self.elspec['nodeName'] in inodes.GetName():
					slicer.mrmlScene.RemoveNode(slicer.util.getNode(inodes.GetID()))

		pts = vtk.vtkPoints()
		pts.SetNumberOfPoints(CH.npoints)
		for i in range(CH.npoints):
			pts.SetPoint(i, CH.points[(i, 0)], CH.points[(i, 1)], CH.points[(i, 2)])

		poly = vtk.vtkPolyData()
		poly.SetPoints(pts)
		delny = vtk.vtkDelaunay3D()
		delny.SetInputData(poly)
		delny.SetTolerance(0.01)
		delny.SetAlpha(10.0)
		delny.BoundingTriangulationOff()
		delny.Update()

		self.final_model = vtk.vtkDataSetSurfaceFilter()
		self.final_model.SetInputConnection(delny.GetOutputPort())
		self.final_model.Update()

		if self.filename is not None:
			writer = vtk.vtkPolyDataWriter()
			writer.SetInputData(self.final_model.GetOutput())
			writer.SetFileName(os.path.join(self.elspec['data_dir'], self.elspec['output_name']))
			if RASsys:
				writer.SetHeader('3D Slicer output. SPACE=RAS')
			else:
				writer.SetHeader('3D Slicer output. SPACE=LPS')
			writer.Update()
			writer.Write()

		self.add_to_scene()

	def add_to_scene(self, returnNode=False):
		if self.nodeName is not None:
			node = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode')
			node.SetAndObservePolyData(self.final_model.GetOutput())
			node.SetName(self.nodeName)
			nodeDisplayNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelDisplayNode')
			node.SetAndObserveDisplayNodeID(nodeDisplayNode.GetID())
		else:
			node = slicer.util.loadModel(os.path.join(self.elspec['data_dir'], self.elspec['output_name']))
			node.SetName(os.path.splitext(os.path.splitext(os.path.basename(self.filename))[0])[0])

		node.GetModelDisplayNode().SetColor(self.elspec['model_col'])
		node.GetModelDisplayNode().SetSelectedColor(self.elspec['model_col'])
		node.GetModelDisplayNode().SetSliceIntersectionVisibility(self.elspec['model_vis'])
		node.GetModelDisplayNode().SetSliceIntersectionOpacity(1)
		node.GetDisplayNode().SetOpacity(0.8)
		
		if returnNode:
			return node
		
		if self.filename is not None:
			slicer.util.saveNode(node, os.path.join(self.elspec['data_dir'], self.filename))


class dotdict(dict):
	"""dot.notation access to dictionary attributes.
	a dictionary that supports dot notation 
	as well as dictionary access notation 
	usage: d = DotDict() or d = DotDict({'val1':'first'})
	set attributes: d.val2 = 'second' or d['val2'] = 'second'
	get attributes: d.val2 or d['val2']
	"""
	__getattr__ = dict.get
	__setattr__ = dict.__setitem__
	__delattr__ = dict.__delitem__

class customEventFilter(qt.QObject):

	def eventFilter(self, obj, event):
		"""
				Event filter for rerouting wheelEvents away from double spin boxes.
				"""
		if event.type() == qt.QEvent.Wheel and isinstance(obj, qt.QDoubleSpinBox):
			event.ignore()
			return True
		else:
			if event.type() == qt.QEvent.Wheel:
				if isinstance(obj, ctk.ctkSliderWidget):
					event.ignore()
					return True
			return False


class customCTKSliderEventFilter(qt.QObject):

	def eventFilter(self, obj, event):
		"""
		Event filter for rerouting wheelEvents away from double spin boxes.
		"""
		if event.type() == qt.QEvent.Wheel and isinstance(obj, ctk.ctkSliderWidget):
			event.ignore()
			return True
		else:
			return False

class customCTKDoubleSliderEventFilter(qt.QObject):

	def eventFilter(self, obj, event):
		"""
		Event filter for rerouting wheelEvents away from double spin boxes.
		"""
		if event.type() == qt.QEvent.Wheel and isinstance(obj, ctk.ctkDoubleSlider):
			event.ignore()
			return True
		else:
			return False

def getReverseTransform(transform, removeOriginal=False):
	"""Returns the reverse of the supplied transform node.

	Parameters
	----------
	transform : dict
		Point 2 coordinates
	
	Returns
	-------
	NormVec : NDArray
		The normal vector of the vector.
	
	"""
	if len(slicer.util.getNodes(f"{transform.GetName()}_reverse")) > 0:
		slicer.mrmlScene.RemoveNode(list(slicer.util.getNodes(f"{transform.GetName()}_reverse").values())[0])
	
	transformMatrix = vtk.vtkGeneralTransform()
	slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(None, transform, transformMatrix)
	t = slicer.mrmlScene.AddNode(slicer.vtkMRMLLinearTransformNode())
	t.SetName(f"{transform.GetName()}_reverse")
	t.ApplyTransform(transformMatrix)
	if removeOriginal:
		slicer.mrmlScene.RemoveNode(transform)

	return t

def fcsvLPStoRAS(fcsv_fname):
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

def writeFCSV(fid_node,fcsv_fname,coord_sys='LPS'):

	with open(fcsv_fname, 'w') as fid:
		fid.write("# Markups fiducial file version = 4.11\n")
		fid.write("# CoordinateSystem = LPS\n")
		fid.write("# columns = id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID\n")

	data_fcsv={
		'id':[],'x':[],'y':[],'z':[],'ow':[],'ox':[],'oy':[],'oz':[],'vis':[],'sel':[],'lock':[],'label':[],'desc':[],'associatedNodeID':[]
	}
	for ifid in range(fid_node.GetNumberOfFiducials()):
		pointCoordsRAS = np.zeros(3)
		fid_node.GetNthControlPointPositionWorld(ifid, pointCoordsRAS)
		if coord_sys == 'LPS':
			pointCoordsRAS=np.array(pointCoordsRAS)*np.array([-1,-1,1])
		fid_label = fid_node.GetNthFiducialLabel(ifid)
		data_fcsv['id'].append(ifid+1)
		data_fcsv['x'].append(pointCoordsRAS[0])
		data_fcsv['y'].append(pointCoordsRAS[1])
		data_fcsv['z'].append(pointCoordsRAS[2])
		data_fcsv['ow'].append(0)
		data_fcsv['ox'].append(0)
		data_fcsv['oy'].append(0)
		data_fcsv['oz'].append(1)
		data_fcsv['vis'].append(1)
		data_fcsv['sel'].append(1)
		data_fcsv['lock'].append(1)
		data_fcsv['label'].append(fid_label)
		data_fcsv['desc'].append('')
		data_fcsv['associatedNodeID'].append('')

	with open(fcsv_fname, 'a') as out_file:
		writer = csv.writer(out_file, delimiter = ",")
		writer.writerows(zip(*data_fcsv.values()))

def rgbToHex(color):
	""" Converts RGB colour to HEX.
	
	Parameters
	----------
	color : list of str
		color to convert
	
	Returns
	-------
	rgb2hex : str
		The HEX color code as str
	
	"""
	r = int(color[0]*255)
	g = int(color[1]*255)
	b = int(color[2]*255)

	rgb2hex = "#{:02x}{:02x}{:02x}".format(r,g,b)
	
	return rgb2hex

def hex2rgb(hx):
	""" Changes colour mode from HEX to RGB.
	
	Parameters
	----------
	color : str
		color in RGB
	
	Returns
	-------
	rgb : tuple
		The RGB equivalent of the given HEX
	
	"""
	rgb = (int(hx[1:3], 16) / 255, int(hx[3:5], 16) / 255, int(hx[5:], 16) / 255)
	return rgb
	
def arrayFromMarkupsControlPointLabels(markupsNode):
	"""Return control point data array of a markups node as numpy array.
	.. warning:: Important: memory area of the returned array is managed by VTK,
	therefore values in the array may be changed, but the array must not be reallocated.
	See :py:meth:`arrayFromVolume` for details.
	"""
	labels=[]
	for measurementIndex in range(markupsNode.GetNumberOfControlPoints()):
		label = markupsNode.GetNthControlPointLabel(measurementIndex)
		labels.append(label)
	return labels

def sorted_nicely(l):
	""" Sorts iterable in the way that is expected.

	Parameters
	----------
	l : list
		The iterable to be sorted.

	Returns
	-------
	sortedList : list
		The sorted iterable.

	"""
	convert = lambda text: int(text) if text.isdigit() else text
	alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
	sortedList = sorted(l, key = alphanum_key)

	return sortedList

def createModelBox(model_name, modelNameDict, modelWig_dict):
	
	if modelNameDict[model_name]['main'] not in list(modelWig_dict):
		modelWig_dict[modelNameDict[model_name]['main']]=[]
	
	if modelNameDict[model_name]['sub'] !="":
		fontSettings = qt.QFont("font-size: 11pt;font-family: Arial")
		fontSettings.setBold(False)
		modelLabel = qt.QLabel(modelNameDict[model_name]['sub'])
		modelLabel.setFont(fontSettings)
		modelLabel.setAlignment(qt.Qt.AlignLeft)

	fontSettings = qt.QFont("font-size: 10pt;font-family: Arial")
	fontSettings.setBold(False)

	left3DCB=qt.QCheckBox()
	left3DCB.setText('Left')
	left3DCB.setFont(fontSettings)
	left3DCB.setObjectName(f'{model_name}Model3DVisLeft')
	left3DCB.setChecked(False)
	left3DCB.setAutoExclusive(False)
	left3DCB.setFixedWidth(68)

	left2DCB=qt.QCheckBox()
	left2DCB.setText('Left')
	left2DCB.setFont(fontSettings)
	left2DCB.setObjectName(f'{model_name}Model2DVisLeft')
	left2DCB.setChecked(False)
	left2DCB.setAutoExclusive(False)
	left2DCB.setFixedWidth(68)

	right3DCB=qt.QCheckBox()
	right3DCB.setText('Right')
	right3DCB.setFont(fontSettings)
	right3DCB.setObjectName(f'{model_name}Model3DVisRight')
	right3DCB.setChecked(False)
	right3DCB.setAutoExclusive(False)
	right3DCB.setFixedWidth(68)

	right2DCB=qt.QCheckBox()
	right2DCB.setText('Right')
	right2DCB.setFont(fontSettings)
	right2DCB.setObjectName(f'{model_name}Model2DVisRight')
	right2DCB.setChecked(False)
	right2DCB.setAutoExclusive(False)
	right2DCB.setFixedWidth(68)

	modelColor = ctk.ctkColorPickerButton()
	modelColor.setObjectName(f'{model_name}ModelVisColor')
	modelColor.displayColorName = False
	modelColor.setFixedWidth(38)

	modelSB=qt.QDoubleSpinBox()
	modelSB.setObjectName(f'{model_name}ModelOpacity')
	modelSB.setFont(fontSettings)
	modelSB.setMinimum(0)
	modelSB.setMaximum(1.0)
	modelSB.setSingleStep(0.1)
	modelSB.setValue(1.0)
	modelSB.setFixedWidth(58)

	modelGridLayout = qt.QGridLayout()
	modelGridLayout.setAlignment(qt.Qt.AlignHCenter)
	#modelGridLayout.setSizePolicy(qt.QSizePolicy.MinimumExpanding)
	#if modelNameDict[model_name]['sub'] !="":
	modelLabel = qt.QLabel(modelNameDict[model_name]['sub']+'  ')
	modelLabel.setFont(qt.QFont("font-size: 10pt;font-family: Arial"))
	modelLabel.setAlignment(qt.Qt.AlignVCenter | qt.Qt.AlignRight)
	modelLabel.setFixedWidth(180)
	modelGridLayout.addWidget(modelLabel,0,0,2,1)
		
	modelGridLayout.addWidget(left3DCB,0,1,1,1)
	modelGridLayout.addWidget(left2DCB,0,2,1,1)
	modelGridLayout.addWidget(right3DCB,1,1,1,1)
	modelGridLayout.addWidget(right2DCB,1,2,1,1)
	modelGridLayout.addWidget(modelColor,0,3,2,1)
	modelGridLayout.addWidget(modelSB,0,4,2,1)

	modelWig = qt.QWidget()
	modelWig.setObjectName(f'{model_name}ModelWig')
	modelWig.setLayout(modelGridLayout)
	
	modelWig_dict[modelNameDict[model_name]['main']].append([model_name,modelWig])

	return modelWig_dict


def addCustomLayouts():

	settingsPanelWidgetInstance = settingsPanelWidget()

	mainWindow = slicer.util.mainWindow()
	mainSettingsPanelWiget = qt.QDockWidget(mainWindow)
	mainSettingsPanelWiget.setFeatures(qt.QDockWidget.DockWidgetClosable + qt.QDockWidget.DockWidgetMovable + qt.QDockWidget.DockWidgetFloatable)
	mainSettingsPanelFrame = qt.QFrame(mainSettingsPanelWiget)
	mainSettingsPanelLayout = qt.QHBoxLayout(mainSettingsPanelFrame)
	mainSettingsPanelLayout.setAlignment(qt.Qt.AlignHCenter | qt.Qt.AlignVCenter)
	mainSettingsPanelLayout.addWidget(settingsPanelWidgetInstance)

	#### Set the settings panel color depending if the user has light/dark theme on
	text_color = slicer.util.findChild(slicer.util.mainWindow(), 'DialogToolBar').children()[3].palette.buttonText().color().name()
	if text_color == '#000000':
		settingsPanelWidgetInstance.setStyleSheet('QWidget::item{background-color: rgb(239,239,239);color: black; border: none;}')
	else:
		settingsPanelWidgetInstance.setStyleSheet('QWidget::item{background-color: rgb(36,36,36);color: white; border: none;}')

	#### Create custom layout that adds side settings panel
	singletonViewFactory = slicer.qSlicerSingletonViewFactory()
	singletonViewFactory.setTagName("settingsSidePanel")
	singletonViewFactory.setWidget(mainSettingsPanelFrame)
	slicer.app.layoutManager().registerViewFactory(singletonViewFactory)

	layoutNode = slicer.app.layoutManager().layoutLogic().GetLayoutNode()
	layoutNode.AddLayoutDescription(slicerLayout, trajectoryGuideLayout)
	layoutNode.AddLayoutDescription(slicerLayoutAxial, trajectoryGuideAxialLayout)

	mainWindow = slicer.util.mainWindow()
	layoutManager = slicer.app.layoutManager()
	layoutNode = layoutManager.layoutLogic().GetLayoutNode()
	viewToolBar = mainWindow.findChild("QToolBar", "ViewToolBar")
	layoutMenu = viewToolBar.widgetForAction(viewToolBar.actions()[0]).menu()
	layoutSwitchActionParent = layoutMenu

	if 'trajectoryGuide' not in [x.text for x in layoutMenu.actions()]:
		layoutSwitchAction = layoutSwitchActionParent.addAction("trajectoryGuide")
		layoutSwitchAction.setData(slicerLayout)
		layoutSwitchAction.setIcon(qt.QIcon(os.path.join(cwd, 'Resources','Icons',"LayouttrajectoryGuide.png")))
	if 'trajectoryGuideAxial' not in [x.text for x in layoutMenu.actions()]:
		layoutSwitchAction = layoutSwitchActionParent.addAction("trajectoryGuideAxial")
		layoutSwitchAction.setData(slicerLayoutAxial)
		layoutSwitchAction.setIcon(qt.QIcon(os.path.join(cwd, 'Resources','Icons',"LayouttrajectoryGuideAxial.png")))

def createElecBox(electrode_number,electrode_name):
	
	fontSettings = qt.QFont("font-size: 11pt;font-family: Arial")
	fontSettings.setBold(False)
	modelLabel = qt.QLabel(electrode_name)
	modelLabel.setFont(fontSettings)
	modelLabel.setAlignment(qt.Qt.AlignVCenter)
	modelLabel.setMinimumWidth(55)

	fontSettings = qt.QFont("font-size: 10pt;font-family: Arial")
	fontSettings.setBold(False)

	negCB=qt.QCheckBox()
	negCB.setText('Neg')
	negCB.setFont(fontSettings)
	negCB.setObjectName(f'contact{str(electrode_number).zfill(2)}Neg')
	negCB.setChecked(False)
	negCB.setAutoExclusive(False)
	negCB.setMinimumWidth(40)

	posCB=qt.QCheckBox()
	posCB.setText('Pos')
	posCB.setFont(fontSettings)
	posCB.setObjectName(f'contact{str(electrode_number).zfill(2)}Pos')
	posCB.setChecked(False)
	posCB.setAutoExclusive(False)
	posCB.setMinimumWidth(40)

	polarityButtonGroup = qt.QButtonGroup()
	polarityButtonGroup.setExclusive(False)
	polarityButtonGroup.addButton(negCB, 0)
	polarityButtonGroup.addButton(posCB, 1)


	ampCombobox=qt.QDoubleSpinBox()
	ampCombobox.setFont(fontSettings)
	ampCombobox.setObjectName(f'contact{str(electrode_number).zfill(2)}Amp')
	ampCombobox.setMinimum(-1000)
	ampCombobox.setMaximum(1000)
	ampCombobox.setSingleStep(1)
	ampCombobox.setValue(0)
	ampCombobox.setFixedWidth(70)

	frqCombobox=qt.QDoubleSpinBox()
	frqCombobox.setFont(fontSettings)
	frqCombobox.setObjectName(f'contact{str(electrode_number).zfill(2)}Freq')
	frqCombobox.setMinimum(-1000)
	frqCombobox.setMaximum(1000)
	frqCombobox.setSingleStep(1)
	frqCombobox.setValue(0)
	frqCombobox.setFixedWidth(70)

	PWCombobox=qt.QDoubleSpinBox()
	PWCombobox.setFont(fontSettings)
	PWCombobox.setObjectName(f'contact{str(electrode_number).zfill(2)}PW')
	PWCombobox.setMinimum(-1000)
	PWCombobox.setMaximum(1000)
	PWCombobox.setSingleStep(1)
	PWCombobox.setValue(0)
	PWCombobox.setFixedWidth(70)

	impCombobox=qt.QDoubleSpinBox()
	impCombobox.setFont(fontSettings)
	impCombobox.setObjectName(f'contact{str(electrode_number).zfill(2)}Imp')
	impCombobox.setMinimum(-10000)
	impCombobox.setMaximum(10000)
	impCombobox.setSingleStep(1)
	impCombobox.setValue(0)
	impCombobox.setFixedWidth(90)

	elecGridLayout = qt.QGridLayout()
	elecGridLayout.setAlignment(qt.Qt.AlignVCenter)
	elecGridLayout.addWidget(modelLabel,0,0,2,1)
	elecGridLayout.addWidget(negCB,0,1,1,1)
	elecGridLayout.addWidget(posCB,1,1,1,1)
	elecGridLayout.addWidget(ampCombobox,0,2,2,1)
	elecGridLayout.addWidget(frqCombobox,0,3,2,1)
	elecGridLayout.addWidget(PWCombobox,0,4,2,1)
	elecGridLayout.addWidget(impCombobox,0,5,2,1)


	elecWig = qt.QWidget()
	elecWig.setObjectName(f'contact{str(electrode_number).zfill(2)}Wig')
	elecWig.setLayout(elecGridLayout)
	
	return elecWig

class imagePopup(qt.QDialog):

	def __init__(self, title, path, parent=None, aspectRatio=None):
		super().__init__(parent)

		self.pic = qt.QLabel()
		self.pic.setWindowTitle(title)
		self.pic.setScaledContents(True)
		pixmap = qt.QPixmap(path)
		if aspectRatio is None:
			pixmap = pixmap.scaled(0.7 * pixmap.size(), qt.Qt.KeepAspectRatio, qt.Qt.SmoothTransformation)
		else:
			pixmap = pixmap.scaled(aspectRatio,aspectRatio, qt.Qt.KeepAspectRatio, qt.Qt.SmoothTransformation)
		self.pic.setPixmap(pixmap)
		self.pic.frameGeometry.moveCenter(qt.QDesktopWidget().availableGeometry().center())
		self.pic.show()


def sortSceneData():

	### Create Subject Hierchy
	shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)

	# Markups
	MarkupsFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Markups")
	shNode.SetItemExpanded(MarkupsFolder, 0)

	# Volumes
	VolumesFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Volumes")
	shNode.SetItemExpanded(VolumesFolder, 0)

	# Transforms
	TransformsFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Transforms")
	shNode.SetItemExpanded(TransformsFolder, 0)

	# Leads
	leadFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Leads")
	shNode.SetItemExpanded(leadFolder, 0)
	preLeadFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Pre")
	shNode.SetItemParent(preLeadFolder, leadFolder)
	shNode.SetItemExpanded(preLeadFolder, 0)
	periLeadFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Peri")
	shNode.SetItemParent(periLeadFolder, leadFolder)
	shNode.SetItemExpanded(periLeadFolder, 0)
	postLeadFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Post")
	shNode.SetItemParent(postLeadFolder, leadFolder)
	shNode.SetItemExpanded(postLeadFolder, 0)

	# Contacts
	contactsFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Contacts")
	preContactsFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Pre")
	shNode.SetItemParent(preContactsFolder, contactsFolder)
	periContactsFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Peri")
	shNode.SetItemParent(periContactsFolder, contactsFolder)
	postContactsFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Post")
	shNode.SetItemParent(postContactsFolder, contactsFolder)

	# Microelectrodes
	microelectrodesFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Microelectrodes")
	preMicroelectrodesFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Pre")
	shNode.SetItemParent(preMicroelectrodesFolder, microelectrodesFolder)
	periMicroelectrodesFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Peri")
	shNode.SetItemParent(periMicroelectrodesFolder, microelectrodesFolder)
	postMicroelectrodesFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Post")
	shNode.SetItemParent(postMicroelectrodesFolder, microelectrodesFolder)

	# STN Activity
	merFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "MER")
	periMERFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Peri")
	shNode.SetItemParent(periMERFolder, merFolder)
	postMERFolder = shNode.CreateFolderItem(shNode.GetSceneItemID(), "Right")
	shNode.SetItemParent(postMERFolder, merFolder)

	# Markups
	if len([x for x in slicer.util.getNodesByClass('vtkMRMLMarkupsFiducialNode')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLMarkupsFiducialNode')]):
			shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), MarkupsFolder)

	if len([x for x in slicer.util.getNodesByClass('vtkMRMLMarkupsLineNode')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLMarkupsLineNode')]):
			shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), MarkupsFolder)

	# Volumes
	if len([x for x in slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')]):
			shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), VolumesFolder)

	# Transforms
	if len([x for x in slicer.util.getNodesByClass('vtkMRMLLinearTransformNode')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLLinearTransformNode')]):
			shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), TransformsFolder)

	#
	### Move Model Items
	#
	if len([x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_lead')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_lead')]):
			if 'ses-pre' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), preLeadFolder)
			elif 'ses-peri' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), periLeadFolder)
			elif 'ses-post' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), postLeadFolder)

	if len([x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_contact')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_contact')]):
			if 'ses-pre' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), preContactsFolder)
			elif 'ses-peri' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), periContactsFolder)
			elif 'ses-post' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), postContactsFolder)

	if len([x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_track')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_track')]):
			if 'ses-pre' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), preMicroelectrodesFolder)
			elif 'ses-peri' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), periMicroelectrodesFolder)
			elif 'ses-post' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), postMicroelectrodesFolder)

	if len([x for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_activity')]) > 0:
		for item in sorted_nicely([x.GetName() for x in slicer.util.getNodesByClass('vtkMRMLModelNode') if x.GetName().endswith('_activity')]):
			if 'ses-peri' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), periMERFolder)
			elif 'ses-post' in item:
				shNode.SetItemParent(shNode.GetItemByDataNode(slicer.util.getNode(item)), postMERFolder)
