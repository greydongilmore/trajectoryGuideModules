cmake_minimum_required(VERSION 3.13.4)

project(trajectoryGuide)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/trajectoryGuide")
set(EXTENSION_CATEGORY "trajectoryGuide")
set(EXTENSION_CONTRIBUTORS "Greydon Gilmore (Western University)")
set(EXTENSION_DESCRIPTION "This is an example of a simple extension")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/trajectoryGuide.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/trajectoryGuide/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(dataImport)
add_subdirectory(frameDetect)
add_subdirectory(registration)
add_subdirectory(anatomicalLandmarks)
add_subdirectory(preopPlanning)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
