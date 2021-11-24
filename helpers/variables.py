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
        'contact_size': 1.5,
        'contact_spacing': 1.5,
        'diameter': 1.1,
        'electrode_1': [0,1,2,3],
        'electrode_2': [8,9,10,11],
        'contact_label':['','','',''],
        'filename': '3387'
     }
electrodeModels['Medtronic 3387'] = medtronic_3387

medtronic_3389 = {
        'num_groups': 4,
        'num_contacts': 4,
        'encapsultation': 1.5,
        'contact_size': 1.5,
        'contact_spacing': 0.5,
        'diameter': 1.1,
        'electrode_1': [0,1,2,3],
        'electrode_2': [8,9,10,11],
        'contact_label':['','','',''],
        'filename': '3389'
     }
electrodeModels['Medtronic 3389'] = medtronic_3389

bsci_directional = {
        'num_groups': 4,
        'num_contacts': 8,
        'encapsultation': 0,
        'contact_size': 1.5,
        'contact_spacing': 0.5,
        'diameter': 1.1,
        'electrode_1': [1,2,3,4,5,6,7,8],
        'electrode_2': [9,10,11,12,13,14,15,16],
        'contact_label':['','seg ','seg ','seg ','seg ','seg ','seg ', ''],
        'filename': 'directional'
     }
electrodeModels['B.Sci. directional'] = bsci_directional

bsci_nondirectional = {
        'num_groups': 8,
        'num_contacts': 8,
        'encapsultation': 1.1,
        'contact_size': 1.5,
        'contact_spacing': 0.5,
        'diameter': 1.1,
        'electrode_1': [1,2,3,4,5,6,7,8],
        'electrode_2': [9,10,11,12,13,14,15,16],
        'contact_label':['','','','','','','', ''],
        'filename': 'nondirectional'
     }

electrodeModels['B.Sci. non-directional'] = bsci_nondirectional


RD10RSP03 = {
        'num_groups': 10,
        'num_contacts': 10,
        'encapsultation': 0.71,
        'contact_size': 2.29,
        'contact_spacing': 0.71,
        'diameter': 0.86,
        'electrode_1': [1,2,3,4,5,6,7,8,9,10],
        'electrode_2': [1,2,3,4,5,6,7,8,9,10],
        'contact_label':['','','','','','','', ''],
        'filename': 'rd10rsp03'
     }
     
electrodeModels['RD10R-SP03X'] = RD10RSP03

RD10RSP04 = {
        'num_groups': 10,
        'num_contacts': 10,
        'encapsultation': 1.71,
        'contact_size': 2.29,
        'contact_spacing': 1.71,
        'diameter': 0.86,
        'electrode_1': [1,2,3,4,5,6,7,8,9,10],
        'electrode_2': [1,2,3,4,5,6,7,8,9,10],
        'contact_label':['','','','','','','', ''],
        'filename': 'rd10rsp04'
     }
     
electrodeModels['RD10R-SP04X'] = RD10RSP04

RD10RSP05 = {
        'num_groups': 10,
        'num_contacts': 10,
        'encapsultation': 2.71,
        'contact_size': 2.29,
        'contact_spacing': 2.71,
        'diameter': 0.86,
        'electrode_1': [1,2,3,4,5,6,7,8,9,10],
        'electrode_2': [1,2,3,4,5,6,7,8,9,10],
        'contact_label':['','','','','','','', ''],
        'filename': 'rd10rsp05'
     }
     
electrodeModels['RD10R-SP05X'] = RD10RSP05

RD10RSP06 = {
        'num_groups': 10,
        'num_contacts': 10,
        'encapsultation': 3.71,
        'contact_size': 2.29,
        'contact_spacing': 3.71,
        'diameter': 0.86,
        'electrode_1': [1,2,3,4,5,6,7,8,9,10],
        'electrode_2': [1,2,3,4,5,6,7,8,9,10],
        'contact_label':['','','','','','','', ''],
        'filename': 'rd10rsp06'
     }
     
electrodeModels['RD10R-SP06X'] = RD10RSP06

RD10RSP07 = {
        'num_groups': 10,
        'num_contacts': 10,
        'encapsultation': 4.71,
        'contact_size': 2.29,
        'contact_spacing': 4.71,
        'diameter': 0.86,
        'electrode_1': [1,2,3,4,5,6,7,8,9,10],
        'electrode_2': [1,2,3,4,5,6,7,8,9,10],
        'contact_label':['','','','','','','', ''],
        'filename': 'rd10rsp07'
     }
     
electrodeModels['RD10R-SP07X'] = RD10RSP07

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
    dict_out['subject']=dictionary['subject']
    dict_out['target']=dictionary['target']
    dict_out['surgeon']=dictionary['surgeon']
    dict_out['surgery_date']=dictionary['surgery_date']
    dict_out['frame_system']=dictionary['frame_system']
    dict_out['trajectories']=dictionary['trajectories']
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