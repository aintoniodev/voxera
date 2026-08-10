Feature: Score CLI
  The voxera CLI evaluates a voice audio file into a Voice Score (CVS 0-100)
  with per-dimension breakdown and a verdict. With --ref it also reports
  Voice Preservation % (resemblyzer). Evaluation ONLY: never modifies audio.

  # Score CLI-01: reports the Voice Score for speech-like audio
  Scenario Outline: Score CLI-01 reports the Voice Score for speech-like audio
    Given the input audio file <input> is speech-like
    When I run voxera score <input>
    Then the exit status is <status>
    And stdout contains <score_header>
    And stdout contains <dimension>

    Examples:
      | input     | score_header | dimension | status |
      | voice.wav | Voice Score  | Dynamics  | 0      |

  # Score CLI-02: --ref reports voice preservation
  Scenario Outline: Score CLI-02 --ref reports voice preservation
    Given the input audio file <input> is speech-like
    When I run voxera score <input> --ref <ref> --format json
    Then the exit status is <status>
    And stdout contains <preservation>

    Examples:
      | input     | ref        | preservation      | status |
      | voice.wav | voice.wav  | voice_preservation| 0      |

  # Score CLI-03: fails cleanly on a missing input
  Scenario Outline: Score CLI-03 fails cleanly on a missing input
    When I run voxera score <input>
    Then the exit status is <status>
    And stderr contains <message>

    Examples:
      | input     | message     | status |
      | nope.wav  | no such file| 1      |
