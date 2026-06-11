# pydroplet

This is a package to interface with the [Droplet](https://shop.hydrificwater.com/pages/buy-droplet) device.

## Getting Started
Install the package from [PyPI](https://pypi.org/project/pydroplet/).
```
pip install pydroplet
```
See the `examples` directory to get started.

## Data
- Flow rate (L/min)
- Volume (mL) - this may be small or negative, as it represents the delta since the last report
- Server connectivity - whether the Droplet is connected to Hydrific servers
- Signal quality - the quality of the ultrasonic signal. If the Droplet is correctly installed on the pipe, this should always be good.
- Leak status ("high_leak") - true if flow is detected that exceeds the threshold set on the Droplet app.
- Unusual flow status ("low_leak") - true if unusual flow is detected, such as a leaky flapper or slow leak.

**Note:**
In order to view leak and unusual flow status, Droplet must be connected to Hydrific servers. All other data is available even if the Droplet is restricted to the local network. Also, Droplet's firmware must be v1.4.0 or greater.
