Feature: Enhance CLI
  The ims CLI enhances a voice audio file through a pluggable backend
  and writes the improved audio to an output file.

  # Enhance CLI-01: enhances a wav file with the default backend and writes the output
  Scenario Outline: Enhance CLI-01 enhances a wav file with the default backend and writes the output
    Given an input wav file exists at <input>
    When the user runs ims enhance <input> -o <output>
    Then the exit status is 0
    And an output wav file exists at <output>
    And the file at <output> is a valid wav
    And the file at <output> differs from the file at <input>

    Examples:
      | input      | output               |
      | sample.wav | sample-enhanced.wav  |
      | podcast.wav| podcast-enhanced.wav |

  # Enhance CLI-02: enhances a wav file with an explicitly selected backend
  Scenario Outline: Enhance CLI-02 enhances a wav file with an explicitly selected backend
    Given an input wav file exists at <input>
    When the user runs ims enhance <input> -o <output> --backend dpdfnet
    Then the exit status is 0
    And an output wav file exists at <output>

    Examples:
      | input       | output              |
      | sample.wav  | sample-explicit.wav |
      | podcast.wav | podcast-explicit.wav|

  # Enhance CLI-03: rejects an unknown backend
  Scenario Outline: Enhance CLI-03 rejects an unknown backend
    Given an input wav file exists at sample.wav
    When the user runs ims enhance sample.wav -o unused.wav --backend <backend>
    Then the exit status is 2
    And the error message names the backend <backend>

    Examples:
      | backend        |
      | bogus          |
      | madeup-engine  |

  # Enhance CLI-04: fails cleanly when the input path does not exist
  Scenario Outline: Enhance CLI-04 fails cleanly when the input path does not exist
    Given no file exists at <input>
    When the user runs ims enhance <input> -o out.wav
    Then the exit status is 1
    And the error message names the input path <input>

    Examples:
      | input           |
      | missing.wav     |
      | nope/voice.wav  |

  # Enhance CLI-05: rejects an unsupported input format
  Scenario Outline: Enhance CLI-05 rejects an unsupported input format
    Given an input file exists at <input> in an unsupported format
    When the user runs ims enhance <input> -o out.wav
    Then the exit status is 1
    And the error message explains that the input format is unsupported

    Examples:
      | input      |
      | notes.txt  |
      | track.mp4  |

  # Enhance CLI-06: rejects an empty audio file
  Scenario: Enhance CLI-06 rejects an empty audio file
    Given an empty wav file exists at empty.wav
    When the user runs ims enhance empty.wav -o out.wav
    Then the exit status is 1
    And the error message explains that the input audio is empty

  # Enhance CLI-07: requires an output path
  Scenario: Enhance CLI-07 requires an output path
    Given an input wav file exists at sample.wav
    When the user runs ims enhance sample.wav
    Then the exit status is 2
    And the error message explains that an output path is required

  # Enhance CLI-08: requires an input file
  Scenario: Enhance CLI-08 requires an input file
    When the user runs ims enhance -o out.wav
    Then the exit status is 2
    And the error message explains that an input file is required
