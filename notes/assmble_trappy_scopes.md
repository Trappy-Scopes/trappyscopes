
# Assemble a trappy scope

Broad steps:

1. Print the frame
2. Assemble the electronics
3. Assmble the frame
4. Install trappy scopes software
5. Done!


## 1. Print the frame

The frame of the trappy scopes 3D-printed opto-mechanical assembly is available at: https://github.com/Trappy-Scopes/trappyframe/ .
The scope can be entirely printed with PLA (recommended PLA 3D860 Black). The frame can be mounted on any standardised 6mm Stainless Steel Rods (X4, recommended length is 50cm for each). The compnents use self tightening flexure mechanisms and do not require thread-inserts. Standardised 3mm and 4mm hex screws (10mm length) are sufficient for most mounts. Additionally, 2.6mm and 1mm small screws are required for mounting of electronics and cameras.

It is recommended that you use no screws while mounting the components on the rods and only use screws for tightening them. Movement of compinents while the screws are tightened leads to faster wear & tear, and faster misalignemnt of frmae rods.


## 2. Assemble the electonics

1. **Raspberry Pi Pico W microcontroller**: A library of trappy-scopes electronics is available at: https://github.com/Trappy-Scopes/electronics . These are easy to assmble PCBs and use Raspberry Pi Pico W as the base microcontroller. A specialised firmware (available at: https://github.com/Trappy-Scopes/pico_firmware) can be used to multiplex between the different software defined configurations. The firware can be flashed from the trappy-scopes scope-cli, once micropython is installed.

Installtion of micropython (recommended) on the pico devies can be done using Thonny IDE: https://thonny.org/ .

2. **Raspberry Pi SoC**: Raspberry Pi OS 64Bit is recommended on micro-SD cards. Instructions can be found here: https://www.raspberrypi.com/documentation/computers/getting-started.html . Suffiecient cooling should be provided to the SoC. To operate trappy-scopes in a parallel scope configuration, refer to the following repositiory: https://github.com/Trappy-Scopes/multiplexed_clusters . 


## 3. Assmble the frame

 We have the frame printed and the electronics ready. So let's assemble a trappy-scopes microscope!

 ## Assemble a single unit

 The instuctions to assemble a single unit are present here:
https://github.com/Trappy-Scopes/trappyframe/blob/main/assembly.md


## Assemble the cluster

The cluster assembly instructions can be found here:
https://github.com/Trappy-Scopes/multiplexed_clusters

## Assemble Controller units

Controller units are additional machines that aggregate many micropython controlled devices on a single linux machine. They provide a terminal to control the devices directly and also aid in network connectivity through the Ethernet interface.

The instructions to make a controller unit can be found here:
https://github.com/Trappy-Scopes/more_screens


## 4. Install trappy scopes software

The homepage of the Trappy-Scopes scope-command/control-line-interface can be found here: https://github.com/Trappy-Scopes/scope-cli.

The instructions to finish the installation are as follows:

```bash
cd ~ ## Home folder or whereever you want it!
git clone https://github.com/Trappy-Scopes/scope-cli
```


Install all required python packages:
```bash
cd scope-cli
./trappyscope --install
```

Flash `pico_firmware` on the micropython devices:

Connect all micropython devices on the machine using serial connection:

```python
## Inside the scope-cli folder
python -i main.py
from core.installer import mpyfirmware
mpyfirmware.scan() ## List all micropython device ports
mpyfirmware.flash(port)
```

You would notice that initally, a lot of errors are thrown by the CLI. This is probably because we have not defined the device configuration yet. Each "scope" needs to be defined in some degree into a `deviceid.yaml` file in the `config` folder.

```yaml
name: MDev           ## Required! And should be the same as the RPi hostname
type: microscope     ## This instucts the software to make a microscope!



assembly:  ## Superficial descriptions of the system, the bracketed entities are distances between components and are optional (useful for opto-mechanics)!


```


5. Done!

The instructions to use the interface can be found on detail at: https://github.com/Trappy-Scopes/scope-cli. In short, all of these are similar:

```python
python -i main.py  ## The very basic
./trappyscope      ## Shorthand optimised call
python viewer.py   ## To have an additional gui interface.
```




