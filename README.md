# Generator for Philips Hue bridge rules based on a simple configuration

Supported sensors:
- Philips Tap switch
- Philips dimmer
- Philips motion sensor
- External input via a CLIP sensor (e.g., bound Eltako Enocean switches and door/window contacts)

A configuration is a list of dictionaries, each dictionary defining behavior for a sensor.


## Sensors

Each dictionary in the configuration must have value for key `type` defining sensor type:
- `state` for a virtual sensor with state (e.g., for multi-click switches)
- `switch` for a Philips Tap switch or dimmer
- `external` for external input
- `contact` for a virtual contact sensor fed by external input actions
- `motion` for motion sensor


### State virtual sensor

Example:
```python
{
    "type": "state",
    "name": "My state",
    "uses": 2,
    "timeout": "00:00:10"
}
```

State sensor is used to store the state of a switch. One state sensor can be used to store two
states in parallel (indicated by `uses: 2`), e.g., for cycling through scenes on `on` button
and cycling between off and nightlight scene on `off` button.

If `timeout` is set, then the state sensor resets to 0 after this timeout (HH:MM:SS).


### Switch sensor

Example:
```python
{
    "type": "switch",
    "name": "My switch",
    "group": "My group",
    "bindings": {
        "tl": { "type": "scene", "configs": [ {"scene": "My scene"} ] },
        "bl": { "type": "scene", "configs": [ {"scene": "off"} ] },
        "tr": { "type": "dim", "value": 50, "tt": 5 },
        "br": { "type": "dim", "value": -50, "tt": 5 }
    }
}
```

This example defines rules for switch `My switch` which operate on group `My group`. Individual
scene actions may operate on different groups, later more on that. This particular example is
for a Philips Tap switch whose sender was inserted into an Eltako frame and mounted on the wall.
It defines actions for individual buttons by symbolic names instead of button IDs.

Following symbolic names are supported:
- `1`, `2`, `3` and `4` for original Philips Tap switch
- `top-left`, `bottom-left`, `top-right` and `bottom-right` or `tl`, `bl`, `tr` and `br` for
  Philips Tap switch sender built into Eltako switch frame and mounted on a wall
- `on`, `on-hold`, `on-release`, `off`, `off-hold`, `off-release`, `brighter`, `brighter-hold`,
  `brighter-release`, `darker`, `darker-hold`, `darker-release`, `off`, `off-hold` and
  `off-release` for Philips dimmer buttons

TODO describe sensor parameter for switch and external and implement it to disable sensor for some time.

### External sensor

Example:
```python
{
    "type": "external",
    "state": "My state",
    "name": "My switch",
    "group": "My room",
    "bindings": {
        "11": {
            "type": "scene",
            "configs": [
                {"scene": "Night"},
                {"scene": "Day"},
                {"scene": "Other"}
            ],
            "times": {
                "T07:00:00/T20:00:00": 1,   # day
                "T20:00:00/T07:00:00": 0    # night
            }
        },
        "12": {
            "type": "scene",
            "stateUse": "secondary",
            "configs": [
                {"scene": "off"},
                {"scene": "Nightlight", "timeout": "00:20:00"}
            ]
        }
    }
}
```

This a bit more complicated example shows the usage of external input. It is very similar to switch
configuration, but instead of button IDs we have values which are set from outside. Values 0 and 1 are
reserved (0 for boot time and 1 for no action).

External input uses CLIP sensor named `ExternalInput`. If such a sensor doesn't exist, it will be created.

Since this particular example uses multi-state buttons, we need a state sensor to store the current
state of the switch to detect multiple presses. You can see that for input `11`, we have three scenes
and two time ranges. When no state is set, then the initial state is chosen based on the time range,
otherwise first scene is used. For input `12`, we have again two scenes. To cycle through these two
scenes, we again use state sensor, but this time the the secondary state (i.e., negative values).
More on this in action types.


### Contact sensor

Example:
```python
{
    "type": "contact",
    "name": "Bathroom door contact",
    "bindings": {
        "open": "1000",
        "closed": "1001"
    } 
}
```

This type of virtual sensor uses only values 0/1 to indicate door or window is open/closed. As there
is no offer from Philips, we can only map external IDs to indicate contact is open or closed. This
example expects contact sensor to send external ID `1000` when the contact opens and ID `1001` when
the contact closes.

Contact sensor is extremely useful to disable motion sensor while door is closed. For example,
bathroom motion sensor might have a timeout of 1 minute, but when someone is in the bathroom
taking a shower, he doesn't want to do it in the dark. The contact sensor can be used to stop
motion sensor from turning off the light.


### Motion sensor

Example:
```python
{
    "type": "motion",
    "name": "Bathroom sensor",
    "group": "Bathroom",
    "timeout": "00:00:45",
    "dimtime": "00:00:15",
    "contact": "Bathroom door contact",
    "state": "Bathroom switch state",
    "bindings": {
        "on": {
            "type": "scene",
            "configs": [ {"scene": "Bright"} ]
        },
        "off": {
            "type": "off"
        }
    }
}
```

A motion sensor turns light on upon motion and off when no motion is detected for some time.
A Philips motion sensor with given name must be registered on the bridge.

Actions specified for `on` binding is executed when the sensor detect the motion. If no motion
is detected, then after a timeout specified by `timeout` parameter the light for the group
is dimmed (currently hard-coded action). After further timeout specified using `dimtime` parameter
(which defaults to 20 seconds) the light is turned on completely. If there is a motion detected
during dim time, the light is restored to full light and the timeout starts anew.

Binding for `off` is optional and defaults to turning off the lights. Binding for `on` is also
optional, if not specified, the lights won't be turned on automatically (just turned off).

If the optional `state` is present, then the sensor with this name will be reset before
turning light on or off.

Optionally, a contact sensor defined in the same configuration can be addressed using `contact`
parameter. When there is no motion detected shortly after closing the door, the light is turned
off, else it is kept on until the door is open again (and then normal rules with timeout apply).
As already mentioned, this is extremely useful for bathroom.

TODO add binding for dimming lights


## Action types

For each binding, there must be an action specified. Currently, following actions are supported:
- `scene` - set scene (supports multi-scene and time-dependent scenes)
- `off` - turn a group of lights off
- `light` - turn a single light on, off or toggle its state
- `dim` - dim up or down a group
- `redirect` - redirect to another action by setting value of `ExternalInput` sensor

### Scene

Example:
```python
{
    "type": "state",
    "name": "My state",
    "uses": 2
},
{
    "type": "switch",
    "state": "My state",
    "name": "My switch",
    "group": "My room",
    "bindings": {
        "2": {
            "type": "scene",
            "configs": [
                {"scene": "Night"},
                {"scene": "Day"},
                {"scene": "Other"}
            ],
            "times": {
                "T07:00:00/T20:00:00": 1,   # day
                "T20:00:00/T07:00:00": 0    # night
            }
        },
        "1": {
            "type": "scene",
            "stateUse": "secondary",
            "configs": [
                {"scene": "off"},
                {"scene": "Nightlight", "timeout": "00:20:00"}
            ]
        }
    }
}
```

Scene action is the most powerful action available. It allows you to specify list of scenes using
`configs` parameter and set of time ranges with scene index in optional `times` parameter. In the
simplest case, there is just a single scene present and no state or times specified.

When multiple scenes are specified, the scene to use depends on the state. Typically, the state is
reset after some timeout, so when the action is repeated (e.g., light switched on), the first scene
is selected. Multiple action triggers (e.g., multiple light switch presses) cycle through scenes
in configuration.

A special scene `off` is used to turn all lights in the group off. In case the entire scene action
should just turn lights off, you can also use action type `off` instead.

If an optional `times` parameter is specified, then instead of starting with the first scene,
the current time is compared against specified intervals and the scene at the associated index
is recalled (0-based, i.e., `Night` scene in the above example has index 0). If there is no
time range for the current time, then no action is triggered.

Additional `timeout` parameter can be specified for a configuration of the scene to turn off lights
after the specified timeout (unless another action was triggered).

NOTE: timeout doesn't work yet.


### Off

Example:
```python
{
	...,
	"bindings": {
        "on": {
            "type": "scene",
            "configs": [ {"scene": "Bright"} ]
        },
        "off": { "type": "off" }
    }
}
```

Use action type `off` to turn lights of the group off. This is shorthand for
`{ "type": "scene", "configs": [ {"scene": "off"} ] }`.


### Light

Example:
```python
{
    "type": "external",
    "name": "Kitchen switch",
    "bindings": {
        "22": { "type": "light", "light": "Kitchen cabinet", "action": "toggle" }
    }
}
```

Light action defines one of the actions for a single light:
- `on` - turn the light on
- `off` - turn the light off
- `toggle` - toggle the state of the light (see example)


### Dim

Example 1:
```python
{
    "type": "switch",
    "name": "My switch",
    "group": "My group",
    "bindings": {
        "tl": { "type": "scene", "configs": [ {"scene": "My scene"} ] },
        "bl": { "type": "scene", "configs": [ {"scene": "off"} ] },
        "tr": { "type": "dim", "value": 50, "tt": 5 },
        "br": { "type": "dim", "value": -50, "tt": 5 }
    }
}
```

This example shows how to configure a simple switch to use left rocker to turn the light
on and off and the right rocker to increase and decrease brightness of the light.


Example 2:
```python
{
    "type": "switch",
    "name": "My dimmer",
    "group": "My group",
    "bindings": {
        "on": { "type": "scene", "configs": [ {"scene": "My scene"} ] },
        "off": { "type": "scene", "configs": [ {"scene": "off"} ] },
        **HueBridge.DIMMER_RULES
    }
}
```

In this a bit more complex example you see configuration of a Philips dimmer. Instead of
explicitly configuring all rules for dimming up and down, simply add `HueBridge.DIMMER_RULES`
to the list of bindings for the dimmer. Then, it's sufficient to configure `on` and `off`
actions.


### Redirect

Example:
```python
{ "type": "redirect", "value": "14" }
```

Redirect action is the simplest one - when the event fires, it simply sets `ExternalInput` to the
specified value, which then triggers another event. This is useful for handling complex actions
of several switches in the same way. E.g., if you have two or more switches in the same room and
they should behave identically, you could configure them identically. But, if one of the buttons
has a complex action (e.g., multi-scene time-based action), then you can implement this action
once as `external` with some ID and simply redirect buttons of all switches to the same action.


## Complete Example

```python
from hue import HueBridge

BRIDGE="192.168.xx.xx"	# set your bridge IP here
API_KEY="xxxx"			# set your API key here

CONFIG_LR = [
    # Switches to manage
    # Redirect to external actions, so we can use more than one switch
    {
        "type": "switch",
        "name": "Livingroom switch",
        "bindings": {
            "tr": { "type": "redirect", "value": "14" },
            "br": { "type": "redirect", "value": "12" }
        }
    },
    # State for cycling the switch
    {
        "type": "state",
        "name": "Livingroom state",
        "uses": 2,
        "timeout": "00:00:10"
    },
    # Actions for input - either external input or via the wall switch
    {
        "type": "external",
        "state": "Livingroom state",
        "name": "Livingroom switch",
        "group": "Livingroom",
        "bindings": {
            "14": {
                "type": "scene",
                "configs": [
                    {"scene": "Evening"},
                    {"scene": "TV"},
                    {"scene": "Bright"},
                    {"scene": "Day"}
                ],
                "times": {
                    "T07:00:00/T16:00:00": 3,   # day
                    "T16:00:00/T07:00:00": 0    # evening
                }
            },
            "12": {
                "type": "scene",
                "stateUse": "secondary",
                "configs": [
                    {"scene": "off"},
                    {"scene": "Night", "timeout": "00:20:00"}
                ]
            },
            # additional action to turn off kitchen light from the living room
            "11": {
                "type": "scene",
                "group": "Kitchen",
                "configs": [
                    {"scene": "off"}
                ]
            }
        }
    }
]

CONFIG_WC = [
    {
        "type": "contact",
        "name": "Bathroom door contact",
        "bindings": {
            "open": "1000",
            "closed": "1001"
        } 
    },
    {
        "type": "motion",
        "name": "Bathroom sensor",
        "group": "Bathroom",
        "timeout": "00:00:45",
        "dimtime": "00:00:15",
        "contact": "Bathroom door contact",
        "bindings": {
            "on": {
                "type": "scene",
                "configs": [ {"scene": "Bright"} ]
            },
            "off": { "type": "off" }
        }
    }
]

if __name__ == '__main__':
    h = HueBridge(BRIDGE, API_KEY)
    h.configure(CONFIG_LR)
    h.configure(CONFIG_WC)
```

This example shows two independent configurations for living room with multi-state scenes
and for bathroom with motion sensor.
