Feature: Silence CLI
  The voxera CLI trims over-long silences between speech (never cutting
  breaths) and reports the original -> cleaned durations. Silent inputs
  abort with VOXERA_NO_SPEECH (exit 20).

  # Silence CLI-01: trims long gaps and writes the cleaned audio
  Scenario Outline: Silence CLI-01 trims long gaps and writes the cleaned audio
    Given the input audio file <input> has long gaps
    When I run voxera silence <input> -o <output> --level <level>
    Then the exit status is <status>
    And the output file <output> exists
    And the output file <output> is a 48 kHz 24-bit mono wav file
    And stdout contains <report_marker>

    Examples:
      | input     | output      | level     | report_marker | status |
      | voice.wav | cleaned.wav | medium    | cleaned       | 0      |
      | voice.wav | cleaned2.wav| aggressive| cleaned       | 0      |

  # Silence CLI-02: aborts on silent input with VOXERA_NO_SPEECH
  Scenario Outline: Silence CLI-02 aborts on silent input
    Given the input audio file <input> is silent
    When I run voxera silence <input> -o <output> --level <level>
    Then the exit status is <status>
    And stderr contains <message>
    And the output file <output> does not exist

    Examples:
      | input   | output  | level  | message            | status |
      | sil.wav | out.wav | medium | no speech detected | 20     |
