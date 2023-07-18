# scope-cli
Control Layer Interface for the Microscopes that sit on the Raspberry Pi.





## An `Experiment`

### File Structure

```
Experiment_name
		|- .experiment 			        (identifier)
		|- experiment.yaml          (event logs)
		|- data1, data2, data3, ... (data - in the repository)
		|- postprocess              (postprocessed data)
		|- analysis                 (analysis results)
```

### Flow of Control

```mermaid
flowchart
	
	subgraph Setup
		Create-ID-files --> Create-folders --> Copy-Payload
	end
	
	subgraph Loading
		load(load events) --> CWD(Change working directory)
	end
	
	subgraph Deletion
		del -.calls.- close("close()") --> Logs(Write event logs to yaml) --> CWDB(Change working <br>dir to original)
	end
	
	Setup --> Loading --> Deletion
```







### Configuration Files

1. `camconfig.yaml` : Contains the camera configuration file for the default mode.
2. `deviceid.yaml` : Contains the  unique identity constants for the device.
3. `common.py`  : Contains common constants for all devices.



###  Current Sequence


```mermaid
flowchart LR
	print-flugg.header --> load-device_id --> complete-all-imports --> connect-pico --> Free-REPL
```



### Connected Hardware

```mermaid
flowchart
	Camera("Camera<br>(cam)")
	Lighst("Lights<br>(lit)")
	
	Pico("RPi Pico<br>(pico)")
	
```


### Device ID

Examplar Device ID file:

```yaml
# Do Not change ----------------
name      : M1
uuid      : "uuid"
type      : microscope
# ------------------------------

hardware:
  pico         : [pico1, "uuid"]
  camera       : [rpi_hq_picam2, "hardware_camera_id"]
  illumination : CA_PWM_RGB_LED_5mm
```

The default mode for parsing a device ID structure is to first cast each field to a container/collection type and enforce the first value as the unique name and the 2nd value, if present, as a **Universal** unique identifier.





### Experiments

1. The `Experiment` class manages the saving of data in  specific folders and logs experiement events.
2. A folder qualifies as an Experiemnt if it contains the `.experiment` file with the UUID of the experiment.
3. The file `<Experiment_name>.yaml` contains the event logs of the experiments.





### TODO

0. `pyboard` seems to be corrupt. Replace it. Or check if the error only persists if no device is connected.
1. Fix Camera selector
2. Clean scope-cli folder.
+ DONE: Fix experiment class
4. Review each function of PiCamera 2 control layer.
+ DONE: Add null pico-device implementation.
+ CANCELLED : Add null-led device option. 
+ CANCELLED: Device declaration before the fluff.header() should dump formatted yaml instead of a python dict.
+ DONE:  Add Living Physics, IGC to the fluff.header().
9. Interpretor ascelation from `python3` to `python`.
10. Fix abcs import issues.
11. Camera Abstract class add `is_open()` method. `configure()` change of kwargs.
+ DONE: Check if `Experiment` class changes current wd of the python kernal.
13. 
