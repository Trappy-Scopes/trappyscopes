# All the Devices in the Trap-Scopes System (Trappy-System)

Design and implementation document.

---

A `BaseDevice` is a group of processors which can be accessed by a single  `shell` (`device.exec()` method) instance and have their own independent operating system/firmware. 

## Hierarchy and connections



```mermaid
graph TD
	abcs.BaseDevice --> LinuxDevice
	abcs.BaseDevice --> MicropythonDevice
		
	LinuxDevice --> RPiLinuxDevice
	LinuxDevice --> *GenericLinuxDevice
	
	MicropythonDevice --> SerialMPDevice
	MicropythonDevice --> NetworkMPDevice
	MicropythonDevice --> NullMPDevice
	
```



### Common Connection Idioms

```mermaid
graph LR
	
LinuxDevice <--USB--> SerialMPDevice
LinuxDevice <--Wifi--> NetworkMPDevice 

LD2[LinuxDevice] <--Ethernet-->LD3[LinuxDevice]

```



## `BaseDevice` specifics

### Shell and "main"

```mermaid
graph LR
	
	LinuxDevice --"connects-to"--> bash-shell --exec_main() --> linuxmain(python-cli\n./scope-cli/main.py or \n./scope-cli/.trappyscope)
	
	MicropythonDevice --"connects-to"--> mpy-shell --exec_main() --> mpymain("create-devices : execfile('main.py')")
```

### Processor Group

The `BaseDevice`handles the processor group and keep tracks of processor consumption and load. A `LinuxDevice` can make the decision to disconnect power on itself under zero prospective load.

### `BaseDevice.Proxy`

All `BaseDevice` instances can  emit proxy devices that are either actual or virtual peripherals that are connected downstream to them. This allows the upstream BaseDevice to directly access them.

```python
```

