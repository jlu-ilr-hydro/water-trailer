# The Water Analysis Trailer for Environmental Research (WATER)<br>
## Control software<br>

This repository contains the custom control software for the Water Analysis Trailer for Environmental Research (WATER). 
The WATER is a trailer-based mobile sampling platform capable of automatically sampling and analysing water from up to 
11 different sources. At present, measurements can be made for stable water isotopes, nitrate, pH, electrical conductivity 
and water temperature. The software manages sample scheduling, acquisition and measurement, communication with measurement devices, 
storage of results in an integrated SQLite database, and system alarms. It also provides a web interface for remote access 
to the WATER.<br><br>

## Table of contents<br>
* preferences -> contains various configuration files. Most important are the configuration file for the WATER and connected devices (sampler.config.yaml), and the sampling schedule (example.schedule.yaml).<br>
* proxies -> contains device modules for use with the "fake sampler" configuration (see Usage). Please note, due to not being able to publish the customised CWS code due to Copyright reasons, the picarro.py script will not work and no "fake picarro" will load on the example web interface <br>
* test -> code for testing functionality of the measurement devices connected to the WATER.
* tools -> contains various helper files. Most important are database_initialise.py (generates the SQLite database and tables) and sampler.py (runs the software).<br>
* trailer -> the heart of the software which controls the WATER. The sub-directories db, devices, logger and webapp contain files related to the SQLite database setup, device interface and control functions, virtual logger functions, and functions for the web interface, respectively.
* web -> everything needed for the front-end of the web interface, which uses HTML5, ECMAScript 5 and jQuery.<br><br>

## Installation<br>
* Clone the git repository.<br>
* Install the necessary Python packages (see requirements.txt).<br>
* Add the water-trailer directory to PYTHONPATH<br>
* For the web interface, install the necessary JavaScript packages. This is achieved by running *npm-install* from the *web* directory.<br><br>

## Usage<br>
To demonstrate functionality, the software can be used with a "fake sampler" configuration. To do this, simply run the following helper Python script:<br><br>
python ./tools/sampler.py <br><br>
The software will automatically recognise that the WATER is not connected and initiate the fake sampler. Optionally, a sampling schedule can be specified. An example
schedule can be found in the *preferences* directory. Schedules must be named *name.schedule.yaml*. To then run the software, the following command is used:<br><br>
python ./tools/sampler.py name<br><br> 
Once the software is running, the web interface will be available at the following address:<br><br>
localhost:20080<br><br>

## Publications<br>
**The base publication for the WATER is...**<br>
Neill, A.J., Windhorst, D., Kraft, P., Sahraei, A., Breuer, L., (in review). A Water Analysis Trailer for Environmental Research (WATER). Hydrology and Earth Systems Sciences.<br><br>

**Publications using the WATER include...***<br>
Sahraei, A., Kraft, P., Windhorst, D. and Breuer, L., 2020. High-resolution, in situ monitoring of stable isotopes of water revealed insight into hydrological response behavior. Water, 12(2), 565; https://doi.org/10.3390/w12020565<br>
Sahraei, A., Chamorro, A., Kraft, P. and Breuer, L., 2021. Application of machine learning models to predict maximum event water fractions in streamflow. Frontiers in Water, 3; https://doi.org/10.3389/frwa.2021.652100<br>
Sahraei, A., Houska, T. and Breuer, L., 2021. Deep learning for isotope hydrology: The application of long short-term memory to estimate high temporal resolution of the stable isotope concentrations in stream and groundwater. Frontiers in Water, 3; https://doi.org/10.3389/frwa.2021.740044<br><br>

## Licence<br>
This software is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.