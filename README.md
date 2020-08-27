# jlohn-mladden
we are all love blaseball

# Development
## Installation
```
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

On OSX, you'll also need to install `pyobjc`. Or you can install `requirements_osx.txt`.

You will need to have python 3.6+ installed

## Usage
```
python jlohn_madden.py
```
This process will run indefinitely and can be exited cleanly with a ctrl+c.

# Quips
Aside from reading the play by play, jlohn can also be configured to play sound effects and say other random quips based on game state. The configuration can be found in `quips.yaml`

## Sound Effects
Defines sounds on disk that can be played. Configured under the `sounds` key.
```
sounds:
  name_of_sound_effect:
    file: path/to/wav/file.wav
    volume: 0.0 // float amount to adjust volume positive or negative
```

## Sound Cues
Defines triggers for playing a sound. Configured under the `sound_cues` key.
```
sound_cues:
  -
    trigger: 'string' //cue this sound if this substring is found in either the play by play or additional quips
    sounds:
      - name_of_sound_effect_1
      - name_of_sound_effect_2 // sound manager will randomly play one of these after the trigger
    delay: 0.0 // float seconds to delay playing sound effect after trigger is found
```

## Quips
Defines additional commentary triggered by play by play and game state. Configured under the `quips` key.
```
quips:
  -
    phrases:
      - 'some phrase to say 1'
      - 'some phrase to say 2'
    // one of trigger_before or trigger_after must be set. If the next play by play contains one of the substrings, jlohn will make this quip
    trigger_before:
      - 'substring in play by play'
    trigger_after:
      - 'substring in play by play'
    args: // optional dict, see below for string interpolation details
      variable_name1: 'game.variable1'
      variable_name2: 'game.variable2'
    chance: 1.0 // optional float 0.0-1.0 probability that this quip will be said if all trigger conditions are meant
    conditions: 'game.variable3 > 0' // optional string equation that will be evaluated if play by play trigger is met
```
### Interpolating dynamic variables into quips
To make jlohn say a dynamic value in a `phrase`, surround an arbitrary variable name with curly braces `{}`. Then in the `args` dict, define the variable name as a key, and as a value put an evaluatable expression. The expressions only have access to a limited set of variables:
* `game` - `BlaseballGlame` object representing the current game state
* `utils` - misc helper functions (ie to determine if a noun needs to be pluralized)
