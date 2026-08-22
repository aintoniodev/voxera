# Smoke acceptance feature: drives the real pipeline (parse -> generate -> run)
# against the voxera CLI error path. Lives under tests/fixtures so it never
# collides with the specifier's feature files in features/.

Feature: voxera CLI error handling
  Scenario: voxera enhance with missing input fails
    Given the input audio file <input> is empty
    When I run voxera enhance <missing> -o <output>
    Then the command fails
    And the exit status is <status>
    And the output file <output> does not exist
    And stderr contains <message>

    Examples:
      | input | missing    | output  | status | message      |
      | a.wav | nope.wav   | out.wav | 1      | no such file |

  Scenario: voxera enhance rejects an unknown backend
    Given the input audio file <input>
    When I run voxera enhance <input> -o <output> --backend <backend>
    Then the command fails
    And stderr contains <message>

    Examples:
      | input  | output  | backend | message        |
      | b.wav  | out.wav | bogus   | unknown backend |
