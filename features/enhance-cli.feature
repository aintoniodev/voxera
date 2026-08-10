Feature: Enhance CLI
  The voxera CLI enhances a voice audio file through a pluggable backend
  and writes the improved audio to an output file. Without --preset the
  command is backend-only (back-compat); with --dsp-only it runs the full
  master pipeline (Track 1).

  # Enhance CLI-01: enhances a wav file with the default backend and writes the output
  Scenario Outline: Enhance CLI-01 enhances a wav file with the default backend and writes the output
    Given the input audio file <input> is speech-like
    When I run voxera enhance <input> -o <output>
    Then the exit status is <status>
    And the output file <output> exists
    And the output file <output> is a wav file
    And the output file <output> differs from the input

    Examples:
      | input       | output              | status |
      | sample.wav  | sample-enhanced.wav | 0      |
      | podcast.wav | podcast-enhanced.wav| 0      |

  # Enhance CLI-02: enhances a wav file with an explicitly selected backend
  Scenario Outline: Enhance CLI-02 enhances a wav file with an explicitly selected backend
    Given the input audio file <input> is speech-like
    When I run voxera enhance <input> -o <output> --backend <backend>
    Then the exit status is <status>
    And the output file <output> exists

    Examples:
      | input      | output             | backend | status |
      | sample.wav | sample-explicit.wav| dpdfnet | 0      |

  # Enhance CLI-03: rejects an unknown backend
  Scenario Outline: Enhance CLI-03 rejects an unknown backend
    Given the input audio file <input> is speech-like
    When I run voxera enhance <input> -o <output> --backend <backend>
    Then the exit status is <status>
    And stderr contains <message>

    Examples:
      | input      | output     | backend       | message         | status |
      | sample.wav | unused.wav | bogus         | unknown backend | 2      |
      | sample.wav | unused.wav | madeup-engine | unknown backend | 2      |

  # Enhance CLI-04: fails cleanly when the input path does not exist
  Scenario Outline: Enhance CLI-04 fails cleanly when the input path does not exist
    When I run voxera enhance <input> -o <output>
    Then the exit status is <status>
    And stderr contains <message>

    Examples:
      | input          | output  | message     | status |
      | missing.wav    | out.wav | no such file| 1      |
      | nope/voice.wav | out.wav | no such file| 1      |

  # Enhance CLI-05: rejects an unsupported input format
  Scenario Outline: Enhance CLI-05 rejects an unsupported input format
    Given the input audio file <input> is not a wav
    When I run voxera enhance <input> -o <output>
    Then the exit status is <status>
    And stderr contains <message>

    Examples:
      | input     | output  | message            | status |
      | notes.txt | out.wav | unsupported format | 1      |

  # Enhance CLI-06: rejects an empty audio file
  Scenario Outline: Enhance CLI-06 rejects an empty audio file
    Given the input audio file <input> is empty
    When I run voxera enhance <input> -o <output>
    Then the exit status is <status>
    And stderr contains <message>

    Examples:
      | input     | output  | message     | status |
      | empty.wav | out.wav | invalid wav | 1      |

  # Enhance CLI-07: requires an output path
  Scenario Outline: Enhance CLI-07 requires an output path
    Given the input audio file <input> is speech-like
    When I run voxera enhance <input>
    Then the exit status is <status>

    Examples:
      | input      | status |
      | sample.wav | 2      |

  # Enhance CLI-08: requires an input file
  Scenario Outline: Enhance CLI-08 requires an input file
    When I run voxera enhance -o <output>
    Then the exit status is <status>

    Examples:
      | output  | status |
      | out.wav | 2      |

  # Enhance CLI-09: --dsp-only runs the pipeline without a neural network
  Scenario Outline: Enhance CLI-09 --dsp-only writes a 48 kHz PCM 24-bit mono wav
    Given the input audio file <input> is speech-like
    When I run voxera enhance <input> -o <output> --dsp-only
    Then the exit status is <status>
    And the output file <output> is a 48 kHz 24-bit mono wav file

    Examples:
      | input      | output        | status |
      | sample.wav | sample-dsp.wav| 0      |

  # Enhance CLI-10: pipeline mode rejects audio without speech (exit 20)
  Scenario Outline: Enhance CLI-10 pipeline mode aborts on silent input
    Given the input audio file <input> is silent
    When I run voxera enhance <input> -o <output> --dsp-only
    Then the exit status is <status>
    And stderr contains <message>
    And the output file <output> does not exist

    Examples:
      | input   | output  | message            | status |
      | sil.wav | out.wav | no speech detected | 20     |
