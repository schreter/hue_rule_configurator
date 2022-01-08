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
    "group": "My group"	# only needed for @off timeout
}
```

State sensor is used to store the state of a switch. One state sensor can be used to store two
states, e.g., positive for cycling through scenes on `on` button and negative for toggling between
off and nightlight scene on `off` button.

State virtual sensor creates one CLIP sensor and optionally one rule to reset the sensor.


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
- `1`, `2`, `3` and `4` for original Hue Tap Switch,
- `top-left`, `bottom-left`, `top-right` and `bottom-right` or `tl`, `bl`, `tr` and `br` for
  Hue Tap Switch sender built into Eltako switch frame and mounted on a wall,
- `on`, `on-hold`, `on-release`, `on-hold-release`, `off`, `off-hold`, `off-release`, `off-hold-release`,
  `brighter`, `brighter-hold`, `brighter-release`, `brighter-hold-release`, `darker`, `darker-hold`,
  `darker-release`, `darker-hold-release`, `off`, `off-hold`, `off-release` and `off-hold-release` for Hue Dimmer,
- `on`, `on-hold`, `on-release` and `on-hold-release` for Hue Smart Button.

Each binding creates by default one rule, except multi-scene and toggle bindings (see later).


### External input

#### Generic external sensor

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
                "T07:00:00/T20:00:00": 2,   # day
                "T20:00:00/T07:00:00": 1    # night
            },
            "reset": "off"
        },
        "12": {
            "type": "scene",
            "value": "Nightlight",
            "timeout": "00:20:00",
            "action": "toggle"
        }
    }
}
```

This a bit more complicated example shows the usage of external input. It is very similar to switch
configuration, but instead of button IDs we have values which are set from outside. Values 0 and 1 are
reserved (0 for boot time and 1 for no action).

External input uses CLIP state sensor named `ExternalInput`. If such a sensor doesn't exist, it will be created.

Since this particular example uses multi-state buttons, we need a state sensor to store the current
state of the switch to detect multiple presses. You can see that for input `11`, we have three scenes
and two time ranges. When no state is set, then the initial state is chosen based on the time range,
otherwise first scene is used. For input `12`, we have a toggle scene. More on this in action types.
This scene resets the state to negative value, so turning on the light will use proper time-based scene.

In order to differentiate between light on and nightlight, an additional rule is needed to reset
the sensor state when the light is turned off and to use sensor state instead of light group on state
to detect that a first press of the button was done. This is indicated by using flag `"reset": "off"`
for the binding of the on button (which normally uses light group on state to determine whether to
trigger the initial action or follow-up action). Note: the additional rule to reset state is really
needed in case when the light was turned off by the app or using a different action (e.g., all lights
off). This is cheaper than adding additional rule per state to detect light off situation.

Same as for switch sensor, each binding creates by default one rule, except multi-scene and toggle
bindings (see later).

#### Contact sensor

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

Contact sensor creates one CLIP sensor and two rules.


#### Where to get external input?

External input can be fed to the Hue Bridge by any external system capable of posting an integer
value to the CLIP status sensor `ExternalInput` (identified by its ID in the respective PUT request).

The author uses a companion project [enocean_to_hue](https://github.com/schreter/enocean_to_hue) to
map commands sent by Enocean switches to integer values and send them to the Hue bridge. Refer to
the documentation of that project for more details.

As hardware, the author uses Eltako FT55R rocker switches and Eltako TF-FKB door/window contact
to generate events, which are then processed by the aforementioned gateway. The advantage is that
it's possible to exchange the actual Enocean hardware in those switches with the one in Philips
Tap buttons, so you can install "reliable" ZigBee inserts into Eltako frames and mount them on
the wall and install "less reliable" Enocean inserts into left-over Philips Tap enclosures.


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

Additionally, it's possible to specify bindings for `dim` and `recover`, which are called on
no motion timeout to dim the lights and to recover light states if motion is detected in the
dimmed state. They by default dim the light by 50% and recover state before dimming. Storing
the light state may wear off the flash memory in lamps quicker, so it's possible to specify
`recover` binding, typically to the same action as `on` action (this can be shortened by specifying
string `"on"` as the action). If `recover` action is specified, then `dim` action will not save
light state. However, since most users will use "recover after power failure" mode for light
bulbs, the state is saved anyway, so there will most likely be no difference in Flash memory
wear when using additional scene to store light state before dimming.

If the optional `state` is present, then the switch state sensor with this name will be reset before
turning light on or off.

Note: if using `on` action for `recover`, you need to pay attention to use `"reset": "off"` flag
for your multi-state scene action for `on`, since otherwise the action will do nothing - the
light is on from the point of view of the on rules.

Optionally, a contact sensor defined in the same configuration can be addressed using `contact`
parameter. When there is no motion detected shortly after closing the door, the light is turned
off, by default after 16 seconds (use `closedchecktime` to override), by first dimming and then
turning it to off, similar to normal timeout handling. Else, it is kept on until the door is
open again (and then normal rules with timeout apply). In case there is no motion detected
initially by mistake (due to reaction time of non-motion detection) and the light dims, motion
in the room will restore the light and won't dim it again until the door is open. Optionally,
if the sensor breaks, a fallback timeout can be specified via `closedtimeout` to turn light off
after specified time of no motion behind closed door. As already mentioned, in sum, this behavior
is extremely useful for bathrooms.

If a motion sensor is used with a switch, then turning off the light while motion is detected
would simply turn the light back on immediately. To prevent this, the motion sensor adds rules
to explicitly disable itself for some time (default 30 seconds, but it can be overridden using
parameter `offtimeout`) when the light is turned off manually (by a switch, external action or
in the app).

Motion sensor creates one CLIP sensor to store sensor state and 6 rules for standard motion handling,
3 rules for integration with switches to properly handle manually turning light on or off and if
a door contact is used, then additional 4 rules for handling door contact. I.e., depending on
the configuration, up to 13 rules are used for a single motion sensor.

It is also possible to use multiple motion sensors for a room. Add `sensors` parameter with the
list of sensor names to use. These sensors will be assigned to the group representing the room and
group's presence and light state will be used instead of the single motion sensor named by `name`.

Note: if the motion sensor is disabled, then the rules won't trigger at all, including timeout
after turning on the light. Reenabling the sensor reenables the rules. The only issue so far is
a bug in Hue bridge which fails to process the no-presence rule if the light is already on and
won't turn it off after a timeout. However, motion in front of the sensor or triggering any
other rules for the sensor (e.g., manually turning off the light) will clean up the state and
the sensor will work as expected.

Sensor `group` indicates the group/room in which the sensor or multiple sensors are located.
This is by default also the light group to control. However, this can be overridden by specifying
`lightgroup` explicitly to a different value. Then, this light group will be checked and
controlled.


## Action types

For each binding, there must be an action specified. Currently, following actions are supported:
- `scene` - set scene (supports multi-scene and time-dependent scenes and toggle with scene)
- `off` - turn a group of lights off
- `light` - turn a single light on, off or toggle its state
- `dim` - dim up or down a group
- `redirect` - redirect to another action by setting value of `ExternalInput` sensor

Note that it is also possible to specify a list of actions for a binding to execute multiple
actions for a single binding (e.g., turn off light in multiple rooms and the like).

### Scene

Example:
```python
{
    "type": "state",
    "name": "My state"
},
{
    "type": "switch",
    "state": "My state",
    "reset": "off",
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
                "T07:00:00/T20:00:00": 2,   # day
                "T20:00:00/T07:00:00": 1    # night
            }
        },
        "1": {
            "type": "scene",
            "value": "Nightlight",
            "timeout": "00:20:00",
            "action": "toggle"
        }
    }
}
```

Scene action is the most powerful action available. It allows you to specify list of scenes using
`configs` parameter and set of time ranges with scene index in optional `times` parameter. In the
simplest case, there is just a single scene present and no state or times specified. For single
scene, instead of `configs` with a single scene, you can also use parameter `value` which names
a single scene.

When multiple scenes are specified, the scene to use depends on the state. Typically, the state is
reset after some timeout, so when the action is repeated (e.g., light switched on), the first scene
is selected. Multiple action triggers (e.g., multiple light switch presses) cycle through scenes
in configuration.

A special scene `off` is used to turn all lights in the group off. In case the entire scene action
should just turn lights off, you can also use action type `off` instead.

If an optional `times` parameter is specified, then instead of starting with the first scene,
the current time is compared against specified intervals and the scene at the associated index
is recalled (1-based, i.e., `Night` scene in the above example has index 1). If there is no
time range for the current time, then no action is triggered. Instead of a single index parameter,
also a structure with `index`, `flag` and `value` can be passed, which will evaluate the Boolean
CLIP flag sensor named by the parameter `flag` and match it against the Boolean value specified
in parameter `value` (and only enable the time range if the value matches). This can be used
to add additional, externally-controlled flags, such as vacation flag, to fine-tune the times
based on user-specific conditions. Note: Since the time range might now have duplicate values,
just add "*<number>" at the end of the time range to discern multiple configurations for the
same time range with different flag values.

Additional `timeout` parameter can be specified for a configuration of the scene to turn off lights
after the specified timeout (unless another action was triggered).

If a scene is set "from the side" by a different switch, you can explicitly set state using
`setstate` parameter in the binding, which sets the index of the scene configured by another
binding using multi-scene action with the same `state` and `group` parameters.

Scenes create one rule per scene, one rule to start default scene or per time range one
rule to start default scene for the time range. I.e., the above example would create 5 rules
for binding 2 and 3 rules for binding 1.

Each timeout to turn off lights in a specified scene after a timeout adds one additional rule.

In addition to normal time and count dependent scene scheduling, it is also possible to set
additional action using `action` parameter. Currently, the only available action is `toggle`
to toggle the light state of a group by setting it to a specific scene if off or turning it
off if on.

Example:
```python
{
    "type": "switch",
    "name": "Kitchen cabinet",
    "bindings": {
        "on": {
            "type": "scene",                # group action 
            "group": "Kitchen cabinet",     # group to manage
            "value": "Concentrate",         # scene to set
            "action": "toggle"              # toggle between on/off states only (single config)
        }
    }
}
```

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

Off action creates one rule.


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

Currently, there is no possibility to specify the light color or intensity when turning it on.

On and off actions create one rule, toggle action creates two rules.


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

Dim action creates one rule.


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

Redirect action creates one rule.


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
                    "T07:00:00/T16:00:00": 4,   # day
                    "T16:00:00/T07:00:00": 1    # evening
                }
            },
            "12": {
                "type": "scene",
                "value": "Night",
                "timeout": "00:20:00",
                "action": "toggle"
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
    h.configure(CONFIG_LR, "Livingroom")
    h.configure(CONFIG_WC, "Bathroom")
```

This example shows two independent configurations for living room with multi-state scenes
and for bathroom with motion sensor. Refer to a complex, documented example in
[hue_rule_generator.py](hue_rule_generator.py) for further real-world examples with detailed
explanation in comments.
