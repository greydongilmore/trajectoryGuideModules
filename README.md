
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]<br />
[![DOI][zenodo-shield]][zenodo-doi]



<!-- PROJECT LOGO -->
<br />
<p align="center">
  <a href="https://github.com/greydongilmore/trajectoryGuide">
    <img src="resources/icons/trajectoryGuide_icon.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">trajectoryGuide</h3>

  <p align="center">
    An open-source software for neurosurgical trajectory planning, visualization, and postoperative assessment
    <br />
    <a href="https://trajectoryguide.greydongilmore.com"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/greydongilmore/trajectoryGuideModules/issues">Report Bug</a>
    ·
    <a href="https://github.com/greydongilmore/trajectoryGuideModules/issues">Request Feature</a>
  </p>
</p>



<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary><h2 style="display: inline-block">Table of Contents</h2></summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgements">Acknowledgements</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

[![trajectoryGuide][trajectoryGuide-screenshot]](https://trajectoryguide.greydongilmore.com)

**trajectoryGuide** provides the capability to plan surgical trajectories within 3D Slicer, an open-source medical imaging software. trajectoryGuide contains modules that span the three phases of neurosurgical trajectory planning.

The main goal of image guidance in neurosurgery is to accurately project magnetic resonance imaging (MRI) and/or computed tomography (CT) data into the operative field for defining anatomical landmarks, pathological structures and margins of tumors. To achieve this, "neuronavigation" software solutions have been developed to provide precise spatial information to neurosurgeons. Safe and accurate navigation of brain anatomy is of great importance when attempting to avoid important structures such as arteries and nerves.

  Neuronavigation software provides orientation information to the surgeon during all three phases of surgery: 1) pre-operative trajectory planning, 2) the intraoperative stereotactic procedure, and 3) post-operative visualization. Trajectory planning is performed prior to surgery using preoperative MRI data. On the day of surgery, the plans are transferred to stereotactic space using a frame or frame-less system. In both instances, a set of radiopaque fiducials are detected, providing the transformation matrix from anatomical space to stereotactic space. During the surgical procedure, the plans are updated according to intraoperative data collected (i.e. microelectrode recordings, electrode stimulation etc.). After the surgery, post-operative MRI or CT imaging confirms the actual position of the trajectory(ies).

### Built With

* Python version: 3.9
* 3D Slicer version: 4.11


<!-- GETTING STARTED -->
## Getting Started

To get a local copy up and running follow these simple steps.

### Prerequisites

#### 3D Slicer

Install 3D Slicer **Version 4.11.0 (or later)** by downloading it from the <a href="https://download.slicer.org/" target="_blank">3D Slicer website</a>.

#### Template space directory

Download the template space files from this <a href="https://github.com/greydongilmore/trajectoryGuideModules/releases/download/space/space.zip" target="_blank">GitHub release</a>. Unzip the folder and move it into the trajectoryGuide folder at the location `resources/ext_libs/space`.

### Installation

Please follow the instructions on the [documentation site](https://trajectoryguide.greydongilmore.com/installation.html).


<!-- USAGE EXAMPLES -->
## Usage

1. **Pre-operative**
   
      - automatic stereotactic frame detection (supported frames: Leksell, BRW)
      - co-registration of MRI scans with 3D volumetric stealth MRI
      
         <p align="center"><img src="resources/imgs/coregConfirmSlide.gif" alt="drawing" width="50%"/></p>
      
      - trajectory planning providing coordinates in anatomical and frame space (including arc, ring angles)

2. **Intra-operative**

      - update final electrode position based on intra-operative testing
      - display microelectrode recordings (MER) within the patients MRI space

3. **Post-operative**

      - co-registration of post-op imaging (CT or MRI)
      - visualization of implanted electrodes (planned, intra-op update, and post-op location)
      - visualize stimulation settings as volume of tissues activated fields
      - view data within a template space (default is MNI space)


<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request


<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE` for more information.


<!-- CONTACT -->
## Contact

Greydon Gilmore - [@GilmoreGreydon](https://twitter.com/GilmoreGreydon) - greydon.gilmore@gmail.com

Project Link: [https://github.com/greydongilmore/trajectoryGuideModules](https://github.com/greydongilmore/trajectoryGuideModules)


<!-- ACKNOWLEDGEMENTS -->
## Acknowledgements

* README format was adapted from [Best-README-Template](https://github.com/othneildrew/Best-README-Template)


<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/greydongilmore/trajectoryGuideModules.svg?style=for-the-badge
[contributors-url]: https://github.com/greydongilmore/trajectoryGuideModules/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/greydongilmore/trajectoryGuideModules.svg?style=for-the-badge
[forks-url]: https://github.com/greydongilmore/trajectoryGuideModules/network/members
[stars-shield]: https://img.shields.io/github/stars/greydongilmore/trajectoryGuideModules.svg?style=for-the-badge
[stars-url]: https://github.com/greydongilmore/trajectoryGuideModules/stargazers
[issues-shield]: https://img.shields.io/github/issues/greydongilmore/trajectoryGuideModules.svg?style=for-the-badge
[issues-url]: https://github.com/greydongilmore/trajectoryGuideModules/issues
[license-shield]: https://img.shields.io/github/license/greydongilmore/trajectoryGuideModules.svg?style=for-the-badge
[license-url]: https://github.com/greydongilmore/trajectoryGuideModules/blob/master/LICENSE.txt
[trajectoryGuide-screenshot]: resources/imgs/main_interface.png
[zenodo-shield]: https://zenodo.org/badge/404597292.svg
[zenodo-doi]: https://zenodo.org/badge/latestdoi/404597292
