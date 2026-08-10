Feature: Restore CLI
  The voxera CLI restores clipped audio (declip), plosive bursts (deplosive)
  and mains hum (dehum) with deterministic heuristics.

  # Restore CLI-01: declips hard-clipped speech-like audio
  Scenario Outline: Restore CLI-01 declips hard-clipped speech-like audio
    Given the input audio file <input> is speech-like clipped
    When I run voxera restore <input> -o <output> --declip
    Then the exit status is <status>
    And the output file <output> exists
    And the output file <output> is a 48 kHz 24-bit mono wav file
    And stdout contains <stage>

    Examples:
      | input      | output      | stage   | status |
      | clip.wav   | fixed.wav   | declip  | 0      |

  # Restore CLI-02: requires at least one restoration stage
  Scenario Outline: Restore CLI-02 requires at least one restoration stage
    Given the input audio file <input> is speech-like
    When I run voxera restore <input> -o <output>
    Then the exit status is <status>
    And stderr contains <message>

    Examples:
      | input     | output  | message       | status |
      | voice.wav | out.wav | at least one  | 1      |
