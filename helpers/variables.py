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
        'num_contacts': 4,
        'encapsultation': 1.5,
        'contact_size': 1.5,
        'contact_spacing': 1.5,
        'electrode_1': [0,1,2,3],
        'electrode_2': [8,9,10,11]
     }
electrodeModels['3387'] = medtronic_3387

medtronic_3389 = {
        'num_contacts': 4,
        'encapsultation': 1.5,
        'contact_size': 1.5,
        'contact_spacing': 0.5,
        'electrode_1': [0,1,2,3],
        'electrode_2': [8,9,10,11]
     }
electrodeModels['3389'] = medtronic_3389

bsci_directional = {
        'num_contacts': 4,
        'encapsultation': 0,
        'contact_size': 1.5,
        'contact_spacing': 0.5,
        'electrode_1': [1,2,3,4,5,6,7,8],
        'electrode_2': [9,10,11,12,13,14,15,16],
        'contact_label':['','seg ','seg ','seg ','seg ','seg ','seg ', '']
     }
electrodeModels['directional'] = bsci_directional

bsci_nondirectional = {
        'num_contacts': 8,
        'encapsultation': 1.1,
        'contact_size': 1.5,
        'contact_spacing': 0.5,
        'electrode_1': [1,2,3,4,5,6,7,8],
        'electrode_2': [9,10,11,12,13,14,15,16],
        'contact_label':['','','','','','','', '']
     }
electrodeModels['non-directional'] = bsci_nondirectional


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