Feature: Master CLI
  The voxera CLI masters a voice audio file through the frozen DSP pipeline
  (no neural network) and writes a 48 kHz PCM 24-bit mono WAV. Silent
  inputs abort with VOXERA_NO_SPEECH (exit 20); --dry-run prints the plan
  and writes nothing.

  # Master CLI-01: masters speech-like audio with the default preset
  Scenario Outline: Master CLI-01 masters speech-like audio with the default preset
    Given the input audio file <input> is speech-like
    When I run voxera master <input> -o <output>
    Then the exit status is <status>
    And the output file <output> exists
    And the output file <output> is a 48 kHz 24-bit mono wav file

    Examples:
      | input     | output       | status |
      | voice.wav | mastered.wav | 0      |

  # Master CLI-02: masters with an explicit preset
  Scenario Outline: Master CLI-02 masters with an explicit preset
    Given the input audio file <input> is speech-like
    When I run voxera master <input> -o <output> --preset <preset>
    Then the exit status is <status>
    And the output file <output> is a 48 kHz 24-bit mono wav file

    Examples:
      | input     | preset   | output               | status |
      | voice.wav | youtube  | mastered-youtube.wav | 0      |
      | voice.wav | podcast  | mastered-podcast.wav | 0      |
      | voice.wav | social   | mastered-social.wav  | 0      |
      | voice.wav | bad-room | mastered-room.wav    | 0      |
      | voice.wav | creator  | mastered-creator.wav | 0      |

  # Master CLI-03: aborts on silent input with VOXERA_NO_SPEECH
  Scenario Outline: Master CLI-03 aborts on silent input
    Given the input audio file <input> is silent
    When I run voxera master <input> -o <output>
    Then the exit status is <status>
    And stderr contains <message>
    And the output file <output> does not exist

    Examples:
      | input   | output  | message            | status |
      | sil.wav | out.wav | no speech detected | 20     |

  # Master CLI-04: --dry-run prints the plan and writes nothing
  Scenario Outline: Master CLI-04 --dry-run prints the plan and writes nothing
    Given the input audio file <input> is speech-like
    When I run voxera master <input> -o <output> --dry-run
    Then the exit status is <status>
    And stdout contains <plan_header>
    And stdout contains <stage>
    And the output file <output> does not exist

    Examples:
      | input     | output  | plan_header | stage     | status |
      | voice.wav | out.wav | VOXERA PLAN | High-pass | 0      |

  # Master CLI-05: 44.1 kHz stereo input is downmixed and resampled to 48 kHz mono
  Scenario Outline: Master CLI-05 stereo 44.1 kHz input becomes 48 kHz mono output
    Given the input audio file <input> is speech-like stereo 44.1 kHz
    When I run voxera master <input> -o <output>
    Then the exit status is <status>
    And the output file <output> is a 48 kHz 24-bit mono wav file

    Examples:
      | input     | output  | status |
      | st441.wav | out.wav | 0      |
