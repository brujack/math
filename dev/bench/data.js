window.BENCHMARK_DATA = {
  "lastUpdate": 1788229391413,
  "repoUrl": "https://github.com/brujack/math",
  "entries": {
    "Benchmark": [
      {
        "commit": {
          "author": {
            "name": "Bruce Jackson",
            "username": "brujack",
            "email": "bjackson@pobox.com"
          },
          "committer": {
            "name": "Bruce Jackson",
            "username": "brujack",
            "email": "bjackson@pobox.com"
          },
          "id": "03ce65d762c14481ca521fa6461c79580e5c232e",
          "message": "docs(spec): retier the notify spec and disposition round 1\n\nOperator decision via relayed architectural review: tier 3 is worth its\ntwo gating dispatches, and all fixes route to the backlog.\n\n- Base rate corrected from \"low\" to unmeasured. Low would license\n  shrinking the design against a known number; unmeasured does not.\n- Row 1 is hedged. The spec recorded the missing negative sample in its\n  Boundary section and then asserted termination as fact in the table.\n- Row 4 splits on artifact/**/mutants.out, which discriminates whether\n  the crate loop began. Upload elides empty directories, so status/\n  absent did not imply what the row claimed.\n- G1 and G2 are named gates, not follow-ups, and need two separate\n  dispatches -- a failing-baseline run cannot answer whether steps[] is\n  backfilled for a reaped job.\n- JOB_NAME removed; select(.name != \"notify\") leaves no duplicated\n  string. New case covers an empty selection.\n- Cases 1 and 10 deleted rather than pinning math#100 and the dedup\n  defect as intended behaviour.\n- --repo moved into the design section, marked contingent on extraction.\n- The gh mock edit is not purely additive; the third edit is named.\n\nDedup defect backlogged with its measurement.\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01Po9r9o7kfJC6LP2x8yva42",
          "timestamp": "2026-08-31T22:59:50Z",
          "url": "https://github.com/brujack/math/commit/03ce65d762c14481ca521fa6461c79580e5c232e"
        },
        "date": 1788229390530,
        "tool": "cargo",
        "benches": [
          {
            "name": "factorial/n=100",
            "value": 70810,
            "range": "± 5106",
            "unit": "ns/iter"
          },
          {
            "name": "factorial/n=1000",
            "value": 127799,
            "range": "± 8257",
            "unit": "ns/iter"
          },
          {
            "name": "factorial/n=5000",
            "value": 334537,
            "range": "± 9988",
            "unit": "ns/iter"
          },
          {
            "name": "pi/digits=100",
            "value": 200269163,
            "range": "± 30989",
            "unit": "ns/iter"
          },
          {
            "name": "pi/digits=1000",
            "value": 200307021,
            "range": "± 48668",
            "unit": "ns/iter"
          },
          {
            "name": "pi/digits=5000",
            "value": 200661466,
            "range": "± 214041",
            "unit": "ns/iter"
          },
          {
            "name": "e/digits=100",
            "value": 200264264,
            "range": "± 24626",
            "unit": "ns/iter"
          },
          {
            "name": "e/digits=1000",
            "value": 200297109,
            "range": "± 59334",
            "unit": "ns/iter"
          },
          {
            "name": "e/digits=5000",
            "value": 200510849,
            "range": "± 71920",
            "unit": "ns/iter"
          },
          {
            "name": "fib/max_digits=100",
            "value": 11289,
            "range": "± 93",
            "unit": "ns/iter"
          },
          {
            "name": "fib/max_digits=1000",
            "value": 142561,
            "range": "± 1676",
            "unit": "ns/iter"
          },
          {
            "name": "fib/max_digits=5000",
            "value": 1796082,
            "range": "± 8158",
            "unit": "ns/iter"
          },
          {
            "name": "collatz/limit=1000",
            "value": 26468,
            "range": "± 759",
            "unit": "ns/iter"
          },
          {
            "name": "collatz/limit=10000",
            "value": 276879,
            "range": "± 697",
            "unit": "ns/iter"
          },
          {
            "name": "collatz/limit=100000",
            "value": 2818276,
            "range": "± 5568",
            "unit": "ns/iter"
          },
          {
            "name": "amicable/limit=10000",
            "value": 57132,
            "range": "± 285",
            "unit": "ns/iter"
          },
          {
            "name": "amicable/limit=100000",
            "value": 788722,
            "range": "± 3054",
            "unit": "ns/iter"
          },
          {
            "name": "amicable/limit=1000000",
            "value": 13011400,
            "range": "± 75091",
            "unit": "ns/iter"
          },
          {
            "name": "prime/limit=10000",
            "value": 200257612,
            "range": "± 19609",
            "unit": "ns/iter"
          },
          {
            "name": "prime/limit=100000",
            "value": 200256465,
            "range": "± 38306",
            "unit": "ns/iter"
          },
          {
            "name": "prime/limit=1000000",
            "value": 200281287,
            "range": "± 118166",
            "unit": "ns/iter"
          },
          {
            "name": "perfect_numbers/limit=10000",
            "value": 838,
            "range": "± 4",
            "unit": "ns/iter"
          },
          {
            "name": "perfect_numbers/limit=1e19",
            "value": 6274,
            "range": "± 366",
            "unit": "ns/iter"
          },
          {
            "name": "perfect_numbers/limit=1e40",
            "value": 21349,
            "range": "± 108",
            "unit": "ns/iter"
          },
          {
            "name": "twin_primes/limit=1000",
            "value": 1457,
            "range": "± 48",
            "unit": "ns/iter"
          },
          {
            "name": "twin_primes/limit=10000",
            "value": 11636,
            "range": "± 121",
            "unit": "ns/iter"
          },
          {
            "name": "twin_primes/limit=100000",
            "value": 168837,
            "range": "± 403",
            "unit": "ns/iter"
          },
          {
            "name": "goldbach/sieve=10000",
            "value": 7041,
            "range": "± 47",
            "unit": "ns/iter"
          },
          {
            "name": "goldbach/sieve=100000",
            "value": 78452,
            "range": "± 264",
            "unit": "ns/iter"
          },
          {
            "name": "goldbach/sieve=1000000",
            "value": 847850,
            "range": "± 4441",
            "unit": "ns/iter"
          },
          {
            "name": "goldbach/pairs=10000",
            "value": 13513237,
            "range": "± 363768",
            "unit": "ns/iter"
          },
          {
            "name": "sq/max_digits=1",
            "value": 3,
            "range": "± 0",
            "unit": "ns/iter"
          },
          {
            "name": "sq/max_digits=2",
            "value": 5,
            "range": "± 0",
            "unit": "ns/iter"
          },
          {
            "name": "sq/max_digits=3",
            "value": 20,
            "range": "± 0",
            "unit": "ns/iter"
          }
        ]
      }
    ]
  }
}