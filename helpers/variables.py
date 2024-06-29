#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jun  9 16:00:43 2019

@author: ggilmore
"""

coordSys = 1

fontSetting = 'font-size: 11pt;font-family: Arial;font-style: normal;'
fontSettingTitle = 'font-size: 12pt;font-family: Arial;font-style: bold;'
fontSettingMainTitle = 'font-size: 16pt;font-family: Arial;font-style: bold;'

groupboxStyle = 'QGroupBox {font-size: 11pt;font-family: Arial;font-style: normal;border: 1px solid gray;border-radius: 0px;margin-top: 0.5em;'
groupboxStyleTitle = 'QGroupBox::title {font-size: 11pt;font-family: Arial;font-style: normal;'

ctkCollapsibleGroupBoxStyle = 'ctkCollapsibleGroupBox {font-size: 11pt;font-family: Arial;font-style: normal;border: 1px solid gray;border-radius: 5px;margin-top: 0.5em;'
ctkCollapsibleGroupBoxTitle = 'ctkCollapsibleGroupBox::title {font-size: 12pt;font-family: Arial;font-style: bold;'

collapsibleWidth = 450
defaultTemplateSpace = 'MNI152NLin2009bAsym'
slicerLayout = 1000
slicerLayoutAxial = 1001

#
#------------------------ Electrode Model Information -------------------------
#
		
electrodeModels = {}
medtronic_3387 = {
		'num_groups': 4,
		'num_contacts': 4,
		'encapsultation': 1.5,
		'diameter': 1.3,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 1.5,
		'electrode_1': [0,1,2,3],
		'electrode_2': [8,9,10,11],
		'contact_label':['','','',''],
		'lead_type': 'linear',
		'filename': '3387'
	 }
electrodeModels['Medtronic 3387'] = medtronic_3387

medtronic_3389 = {
		'num_groups': 4,
		'num_contacts': 4,
		'encapsultation': 1.5,
		'diameter': 1.3,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 0.5,
		'electrode_1': [0,1,2,3],
		'electrode_2': [8,9,10,11],
		'contact_label':['','','',''],
		'lead_type': 'linear',
		'filename': '3389'
	 }
electrodeModels['Medtronic 3389'] = medtronic_3389

medtronic_33005 = {
		'num_groups': 4,
		'num_contacts': 8,
		'encapsultation': 1.0,
		'diameter': 1.36,
		'lead_thickness': 0.2,
		'lead_shift': 1.0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 0.5,
		'electrode_1': [0,1,2,3,4,5,6,7],
		'electrode_2': [8,9,10,11,12,13,14,15],
		'contact_label':['','','',''],
		'lead_type': 'directional',
		'filename': '33005'
	 }
electrodeModels['Medtronic 33005'] = medtronic_33005

medtronic_33015 = {
		'num_groups': 4,
		'num_contacts': 8,
		'encapsultation': 1.0,
		'diameter': 1.36,
		'lead_thickness': 0.2,
		'lead_shift':1.0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 1.5,
		'electrode_1': [0,1,2,3,4,5,6,7],
		'electrode_2': [8,9,10,11,12,13,14,15],
		'contact_label':['','','',''],
		'lead_type': 'directional',
		'filename': '33015'
	 }
electrodeModels['Medtronic 33015'] = medtronic_33015

bsci_directional = {
		'num_groups': 4,
		'num_contacts': 8,
		'encapsultation': 0,
		'diameter': 1.3,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 0.5,
		'electrode_1': [1,2,3,4,5,6,7,8],
		'electrode_2': [9,10,11,12,13,14,15,16],
		'contact_label':['','seg ','seg ','seg ','seg ','seg ','seg ', ''],
		'lead_type': 'directional',
		'filename': 'directional'
	 }
electrodeModels['B.Sci. directional'] = bsci_directional

bsci_nondirectional = {
		'num_groups': 8,
		'num_contacts': 8,
		'encapsultation': 1.1,
		'diameter': 1.3,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 0.5,
		'electrode_1': [1,2,3,4,5,6,7,8],
		'electrode_2': [9,10,11,12,13,14,15,16],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'linear',
		'filename': 'nondirectional'
	 }

electrodeModels['B.Sci. non-directional'] = bsci_nondirectional


sjm_directional_005 = {
		'num_groups': 4,
		'num_contacts': 8,
		'encapsultation': 0,
		'diameter': 1.29,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 0.5,
		'electrode_1': [1,2,3,4,5,6,7,8],
		'electrode_2': [9,10,11,12,13,14,15,16],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'directional',
		'filename': 'sjmdirectional005'
	 }
electrodeModels['SJM Directional 005'] = sjm_directional_005

sjm_directional_015 = {
		'num_groups': 4,
		'num_contacts': 8,
		'encapsultation': 0,
		'diameter': 1.29,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.3,
		'contact_size': 1.5,
		'contact_inflate': .05,
		'contact_spacing': 1.5,
		'electrode_1': [1,2,3,4,5,6,7,8],
		'electrode_2': [9,10,11,12,13,14,15,16],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'directional',
		'filename': 'sjmdirectional015'
	 }
electrodeModels['SJM Directional 015'] = sjm_directional_015

RD10RSP03 = {
		'num_groups': 10,
		'num_contacts': 10,
		'encapsultation': 1.0,
		'diameter': 0.86,
		'lead_thickness': 0.1,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.1,
		'contact_size': 2.29,
		'contact_inflate': 0.1,
		'contact_spacing': [0.71,0.71,0.71,0.71,0.71,0.71,0.71,0.71,0.71],
		'electrode_1': [1,2,3,4,5,6,7,8,9,10],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'linear',
		'filename': 'rd10rsp03'
	 }
	 
electrodeModels['RD10R-SP03X'] = RD10RSP03

RD10RSP04 = {
		'num_groups': 10,
		'num_contacts': 10,
		'encapsultation': 1.0,
		'diameter': 0.86,
		'lead_thickness': 0.1,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.1,
		'contact_size': 2.29,
		'contact_inflate': 0.1,
		'contact_spacing': [1.71,1.71,1.71,1.71,1.71,1.71,1.71,1.71,1.71],
		'electrode_1': [1,2,3,4,5,6,7,8,9,10],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'linear',
		'filename': 'rd10rsp04'
	 }
	 
electrodeModels['RD10R-SP04X'] = RD10RSP04

RD10RSP05 = {
		'num_groups': 10,
		'num_contacts': 10,
		'encapsultation': 1.0,
		'diameter': 0.86,
		'lead_thickness': 0.1,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.1,
		'contact_size': 2.29,
		'contact_inflate': 0.1,
		'contact_spacing': [2.71,2.71,2.71,2.71,2.71,2.71,2.71,2.71,2.71],
		'electrode_1': [1,2,3,4,5,6,7,8,9,10],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'linear',
		'filename': 'rd10rsp05'
	 }
	 
electrodeModels['RD10R-SP05X'] = RD10RSP05

RD10RSP06 = {
		'num_groups': 10,
		'num_contacts': 10,
		'encapsultation': 1.0,
		'diameter': 0.86,
		'lead_thickness': 0.1,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.1,
		'contact_size': 2.29,
		'contact_inflate': 0.1,
		'contact_spacing':[3.71,3.71,3.71,3.71,3.71,3.71,3.71,3.71,3.71],
		'electrode_1': [1,2,3,4,5,6,7,8,9,10],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'linear',
		'filename': 'rd10rsp06'
	 }
	 
electrodeModels['RD10R-SP06X'] = RD10RSP06

MM16DSP05 = {
		'num_groups': 8,
		'num_contacts': 8,
		'encapsultation': 1.5,
		'diameter': 1.3,
		'lead_thickness': 0.2,
		'lead_shift':1.5,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.29,
		'contact_inflate': 0.1,
		'contact_spacing': [2.71,2.71,2.71,2.71,2.71,2.71,2.71,2.71,2.71],
		'electrode_1': [1,2,3,4,5,6,7,8],
		'electrode_2': [1,2,3,4,5,6,7,8],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'linear',
		'filename': 'mm16dsp05'
	 }
	 
electrodeModels['MM16D-SP05X'] = MM16DSP05

BF09RSP51X = {
		'num_groups': 9,
		'num_contacts': 9,
		'encapsultation': 1.5,
		'diameter': 1.28,
		'lead_thickness': 0.2,
		'lead_shift':1.5,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 1.6,
		'contact_inflate': 0.1,
		'contact_spacing': [1.4, 3.4, 3.4, 3.4, 3.4, 3.4, 3.4, 3.4],
		'electrode_1': [1,2,3,4,5,6,7,8],
		'electrode_2': [1,2,3,4,5,6,7,8],
		'contact_label':['','','','','','','', ''],
		'lead_type': 'linear',
		'filename': 'bf09rsp51x'
	 }
	 
electrodeModels['BF09R-SP51X'] = BF09RSP51X

D0805AM = {
		'num_groups': 5,
		'num_contacts': 5,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5],
		'electrode_2': [1,2,3,4,5],
		'contact_label':['','','','',''],
		'lead_type': 'linear',
		'filename': 'd0805am'
	 }

electrodeModels['D08-05AM'] = D0805AM

D0808AM = {
		'num_groups': 8,
		'num_contacts': 8,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5,6,7,8],
		'electrode_2': [1,2,3,4,5,6,7,8],
		'contact_label':['','','','','','','',''],
		'lead_type': 'linear',
		'filename': 'd0808am'
	 }

electrodeModels['D08-08AM'] = D0808AM

D0810AM = {
		'num_groups': 10,
		'num_contacts': 10,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5,6,7,8,9,10],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10],
		'contact_label':['','','','','','','','','',''],
		'lead_type': 'linear',
		'filename': 'd0810am'
	 }

electrodeModels['D08-10AM'] = D0810AM

D0812AM = {
		'num_groups': 12,
		'num_contacts': 12,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5,6,7,8,9,10,11,12],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10,11,12],
		'contact_label':['','','','','','','','','','','',''],
		'lead_type': 'linear',
		'filename': 'd0812am'
	 }

electrodeModels['D08-12AM'] = D0812AM

D0815AM = {
		'num_groups': 15,
		'num_contacts': 15,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
		'contact_label':['','','','','','','','','','','','','','',''],
		'lead_type': 'linear',
		'filename': 'd0815am'
	 }

electrodeModels['D08-15AM'] = D0815AM

D0818AM = {
		'num_groups': 18,
		'num_contacts': 18,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18],
		'contact_label':['','','','','','','','','','','','','','','','','',''],
		'lead_type': 'linear',
		'filename': 'd0818am'
	 }

electrodeModels['D08-18AM'] = D0818AM

D0815BM = {
		'num_groups': 15,
		'num_contacts': 15,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5, 7.0, 1.5, 1.5, 1.5, 1.5, 7.0, 1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
		'contact_label':['','','','','','','','','','','','','','',''],
		'lead_type': 'linear',
		'filename': 'd0815bm'
	 }

electrodeModels['D08-15BM'] = D0815BM

D0815CM = {
		'num_groups': 15,
		'num_contacts': 15,
		'encapsultation': 0,
		'diameter': 0.8,
		'lead_thickness': 0.2,
		'lead_shift':0,
		'lead_tail': 15,
		'contact_thickness': 0.2,
		'contact_size': 2.0,
		'contact_inflate': .1,
		'contact_spacing': [1.5, 1.5, 1.5, 1.5, 11.0, 1.5, 1.5, 1.5, 1.5, 11.0, 1.5, 1.5, 1.5, 1.5],
		'diameter': 0.8,
		'electrode_1': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
		'electrode_2': [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
		'contact_label':['','','','','','','','','','','','','','',''],
		'lead_type': 'linear',
		'filename': 'd0815cm'
	 }

electrodeModels['D08-15CM'] = D0815CM

microelectrodeModels = {
		'probes':{
				'AO 3mm MicroMacro 25 above':'alphaomega-neuroprobe_micromacro-3mm_above-25mm.stl',
				'AO 10mm MicroMacro 25 above':'alphaomega-neuroprobe_micromacro-10mm_above-25mm.stl'
		},
		'default':'AO 10mm MicroMacro 25 above'
}

#
#-------------------------------- JSON Files ----------------------------------
#

def surgical_info_dict(dictionary):
	dict_out=dict()
	dict_out['subject']=dictionary['subject'] if 'subject' in list(dictionary) else []
	dict_out['target']=dictionary['target'] if 'target' in list(dictionary) else []
	dict_out['surgeon']=dictionary['surgeon'] if 'surgeon' in list(dictionary) else []
	dict_out['surgery_date']=dictionary['surgery_date'] if 'surgery_date' in list(dictionary) else []
	dict_out['frame_system']=dictionary['frame_system'] if 'frame_system' in list(dictionary) else []
	dict_out['trajectories']=dictionary['trajectories'] if 'trajectories' in list(dictionary) else []
	return dict_out

def plan_info_dict(dictionary):
	dict_out=dict()
	dict_out['side']=dictionary['side'] if 'side' in list(dictionary) else []
	dict_out['pre']=pre_info_dict({})
	dict_out['intra']=intra_info_dict({})
	dict_out['post']=post_info_dict({})
	return dict_out

def pre_info_dict(dictionary):
	dict_out=dict()
	dict_out['entry']=dictionary['entry'] if 'entry' in list(dictionary) else []
	dict_out['target']=dictionary['target'] if 'target' in list(dictionary) else []
	dict_out['origin_point']=dictionary['origin_point'] if 'origin_point' in list(dictionary) else []
	dict_out['chansUsed']=dictionary['chansUsed'] if 'chansUsed' in list(dictionary) else []
	dict_out['chanIndex']=dictionary['chanIndex'] if 'chanIndex' in list(dictionary) else []
	dict_out['elecUsed']=dictionary['elecUsed'] if 'elecUsed' in list(dictionary) else []
	dict_out['microUsed']=dictionary['microUsed'] if 'microUsed' in list(dictionary) else []
	dict_out['traj_len']=dictionary['traj_len'] if 'traj_len' in list(dictionary) else []
	dict_out['axial_ang']=dictionary['axial_ang'] if 'axial_ang' in list(dictionary) else []
	dict_out['sag_ang']=dictionary['sag_ang'] if 'sag_ang' in list(dictionary) else []
	dict_out['frame_entry']=dictionary['frame_entry'] if 'frame_entry' in list(dictionary) else []
	dict_out['frame_target']=dictionary['frame_target'] if 'frame_target' in list(dictionary) else []
	dict_out['mer_tracks']=dictionary['mer_tracks'] if 'mer_tracks' in list(dictionary) else {}
	return dict_out

def intra_info_dict(dictionary):
	dict_out=dict()
	dict_out['entry']=dictionary['entry'] if 'entry' in list(dictionary) else []
	dict_out['target']=dictionary['target'] if 'target' in list(dictionary) else []
	dict_out['lead_traj_chosen']=dictionary['lead_traj_chosen'] if 'lead_traj_chosen' in list(dictionary) else []
	dict_out['lead_depth']=dictionary['lead_depth'] if 'lead_depth' in list(dictionary) else []
	dict_out['mer_tracks']=dictionary['mer_tracks'] if 'mer_tracks' in list(dictionary) else {}
	return dict_out

def post_info_dict(dictionary):
	dict_out=dict()
	dict_out['entry']=dictionary['entry'] if 'entry' in list(dictionary) else []
	dict_out['target']=dictionary['target'] if 'target' in list(dictionary) else []
	dict_out['lead_traj_chosen']=dictionary['lead_traj_chosen'] if 'lead_traj_chosen' in list(dictionary) else []
	dict_out['lead_depth']=dictionary['lead_depth'] if 'lead_depth' in list(dictionary) else []
	dict_out['mer_tracks']=dictionary['mer_tracks'] if 'mer_tracks' in list(dictionary) else {}
	return dict_out

#
#------------------------------ Data Visibiltiy -------------------------------
#

dataVisibility= {
		'plannedLeadSliceVis': True,
		'actualLeadSliceVis': True,
		'plannedContactSliceVis': True,
		'actualContactSliceVis': True,
		'plannedMERTrackSliceVis': True,
		'actualMERTrackSliceVis': True,
		'plannedSTNMERSliceVis': True,
		'actualSTNMERSliceVis': True
	 }

#
#-------------------------------- Layout ---------------------------------
#

trajectoryGuideLayout = (
			"<layout type=\"horizontal\">"
			" <item>"
			"  <settingsSidePanel></settingsSidePanel>"
			" </item>"
			" <item>"
			"  <layout type=\"vertical\">"
			"   <item>"
			"    <layout type=\"horizontal\">"
			"     <item>"
			"      <view class=\"vtkMRMLSliceNode\" singletontag=\"Red\">"
			"       <property name=\"orientation\" action=\"default\">Axial</property>"
			"       <property name=\"viewlabel\" action=\"default\">R</property>"
			"       <property name=\"viewcolor\" action=\"default\">#F34A33</property>"
			"      </view>"
			"     </item>"
			"     <item>"
			"      <view class=\"vtkMRMLViewNode\" singletontag=\"1\">"
			"       <property name=\"viewlabel\" action=\"default\">1</property>"
			"      </view>"
			"     </item>"
			"    </layout>"
			"   </item>"
			"   <item>"
			"    <layout type=\"horizontal\">"
			"     <item>"
			"      <view class=\"vtkMRMLSliceNode\" singletontag=\"Yellow\">"
			"       <property name=\"orientation\" action=\"default\">Sagittal</property>"
			"       <property name=\"viewlabel\" action=\"default\">Y</property>"
			"       <property name=\"viewcolor\" action=\"default\">#EDD54C</property>"
			"      </view>"
			"     </item>"
			"     <item>"
			"      <view class=\"vtkMRMLSliceNode\" singletontag=\"Green\">"
			"       <property name=\"orientation\" action=\"default\">Coronal</property>"
			"       <property name=\"viewlabel\" action=\"default\">G</property>"
			"       <property name=\"viewcolor\" action=\"default\">#6EB04B</property>"
			"      </view>"
			"     </item>"
			"    </layout>"
			"   </item>"
			"  </layout>"
			" </item>"
			"</layout>"
		)

trajectoryGuideAxialLayout = (
			"<layout type=\"horizontal\">"
			" <item>"
			"  <settingsSidePanel></settingsSidePanel>"
			" </item>"
			" <item>"
			"      <view class=\"vtkMRMLSliceNode\" singletontag=\"Red\">"
			"       <property name=\"orientation\" action=\"default\">Axial</property>"
			"       <property name=\"viewlabel\" action=\"default\">R</property>"
			"       <property name=\"viewcolor\" action=\"default\">#F34A33</property>"
			"      </view>"
			"     </item>"
			"</layout>"
		)

#
#------------------------------ Module Dictionary -------------------------------
#

module_dictionary= {
	'01: Data Import': 'dataImport',
	'02: Frame Detection': 'frameDetect',
	'03: Registration':'registration',
	'04: Anatomical Landmarks': 'anatomicalLandmarks',
	'05: Preop Planning': 'preopPlanning',
	'06: Intraop Planning': 'intraopPlanning',
	'07: Postop Localization': 'postopLocalization',
	'08: Postop Programming': 'postopProgramming',
	'Data View': 'dataView'
 }
 
