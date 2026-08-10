Feature: Analyze CLI
  The voxera CLI analyzes a wav file (never modifies audio) and reports
  loudness, voice, spectral, room and artifact metrics as JSON with a
  provenance system block. Analysis works even without speech.

  # Analyze CLI-01: reports JSON metrics for speech-like audio
  Scenario Outline: Analyze CLI-01 reports JSON metrics for speech-like audio
    Given the input audio file <input> is speech-like
    When I run voxera analyze <input> --format json
    Then the exit status is <status>
    And stdout contains <loudness_key>
    And stdout contains <voice_key>
    And stdout contains <artifact_key>
    And stdout contains <provenance_key>

    Examples:
      | input     | loudness_key    | voice_key    | artifact_key | provenance_key | status |
      | voice.wav | integrated_lufs | speech_ratio | noise_type   | voxera_version | 0      |

  # Analyze CLI-02: works on silent audio (analysis-only never aborts)
  Scenario Outline: Analyze CLI-02 works on silent audio
    Given the input audio file <input> is silent
    When I run voxera analyze <input> --format json
    Then the exit status is <status>
    And stdout contains <voice_key>

    Examples:
      | input   | voice_key    | status |
      | sil.wav | speech_ratio | 0      |

  # Analyze CLI-03: fails cleanly on a missing input
  Scenario Outline: Analyze CLI-03 fails cleanly on a missing input
    When I run voxera analyze <input> --format json
    Then the exit status is <status>
    And stderr contains <message>

    Examples:
      | input    | message     | status |
      | nope.wav | no such file| 1      |
