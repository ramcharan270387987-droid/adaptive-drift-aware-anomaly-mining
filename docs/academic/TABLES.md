# Academic tables

The CSV companions preserve source values. Markdown rates are displayed to at most nine significant digits. The receipt was verified before export. [Sealed evaluation](../final_evaluation.md) · [Sustained benchmark](../SUSTAINED_STREAMING.md)

## Table A. Static anomaly baselines

Primary synthetic holdout. Rates are fractions and AP is average precision. [CSV](tables/table_a.csv)

| Method | Precision | Recall | F1 | FPR | AP | Post-drift FP |
| --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 0.0245385791 | 0.966333333 | 0.0478617803 | 0.0601155451 | 0.747973289 | 216,554 |
| Isolation Forest | 0.00392700256 | 0.999 | 0.00782325244 | 0.396546948 | 0.0212793453 | 1,056,891 |
| Local Outlier Factor | 0.00779234035 | 0.9925 | 0.015463275 | 0.197771779 | 0.549453704 | 633,944 |

## Table B. Drift detector comparison

Aligned synthetic development. Both detectors were evaluated on 500 streams and 640 true transitions. Delay is in observations. [CSV](tables/table_b.csv)

| Detector | Detected | True transitions | Unmatched alarms | Median delay | Mean delay |
| --- | --- | --- | --- | --- | --- |
| ADWIN | 640 | 640 | 142 | 63 | 66.7 |
| Page-Hinkley | 640 | 640 | 1,066 | 36.5 | 46.5859375 |

## Table C. Adaptation comparison

Primary synthetic holdout. Event-window FPR is a pooled fraction. Post-drift counts cover the longer post-drift segment. [CSV](tables/table_c.csv)

| Policy | Event-window FPR | Post-drift FP | Recall | FN | Refits |
| --- | --- | --- | --- | --- | --- |
| Static Z-score | 0.0892433461 | 216,554 | 0.966333333 | 202 | 0 |
| Fixed schedule | 0.0518139178 | 24,872 | 0.9795 | 123 | 15,000 |
| Immediate ADWIN | 0.0205822704 | 26,631 | 0.951833333 | 289 | 1,534 |
| ADWIN + persistence | 0.0398196653 | 17,205 | 0.977166667 | 137 | 1,430 |
| Full selective policy | 0.0744712506 | 56,768 | 0.987666667 | 74 | 1,326 |

## Table D. Final synthetic holdout

Each method scored 3,840,000 observations. TP, FP, TN and FN are point counts; FPR covers every nominal scored point. [CSV](tables/table_d.csv)

| Method | TP | FP | TN | FN | Precision | Recall | F1 | FPR | AP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 5,798 | 230,483 | 3,603,517 | 202 | 0.0245385791 | 0.966333333 | 0.0478617803 | 0.0601155451 | 0.747973289 |
| Isolation Forest | 5,994 | 1,520,361 | 2,313,639 | 6 | 0.00392700256 | 0.999 | 0.00782325244 | 0.396546948 | 0.0212793453 |
| Local Outlier Factor | 5,955 | 758,257 | 3,075,743 | 45 | 0.00779234035 | 0.9925 | 0.015463275 | 0.197771779 | 0.549453704 |
| Fixed schedule | 5,877 | 34,556 | 3,799,444 | 123 | 0.145351569 | 0.9795 | 0.253138931 | 0.00901304121 | 0.900274189 |
| Immediate ADWIN | 5,711 | 34,855 | 3,799,145 | 289 | 0.140782922 | 0.951833333 | 0.24528626 | 0.00909102765 | 0.879797257 |
| ADWIN + persistence | 5,863 | 28,394 | 3,805,606 | 137 | 0.171147503 | 0.977166667 | 0.291278535 | 0.00740584246 | 0.896425852 |
| Persistence + filtering | 5,935 | 65,041 | 3,768,959 | 65 | 0.0836198151 | 0.989166667 | 0.154203908 | 0.0169642671 | 0.829013116 |
| Full selective policy | 5,926 | 69,547 | 3,764,453 | 74 | 0.0785181456 | 0.987666667 | 0.145471506 | 0.0181395409 | 0.820662093 |
| Frozen Z-score + ADWIN | 5,798 | 230,483 | 3,603,517 | 202 | 0.0245385791 | 0.966333333 | 0.0478617803 | 0.0601155451 | 0.747973289 |
| Frozen Z-score + Page–Hinkley | 5,798 | 230,483 | 3,603,517 | 202 | 0.0245385791 | 0.966333333 | 0.0478617803 | 0.0601155451 | 0.747973289 |

## Table E. Final NAB evaluation

Five held-out series, 41,326 scored observations and 13 annotated points or eligible windows per method. A window hit can occur without an exact-point detection. [CSV](tables/table_e.csv)

| Method | TP | FP | TN | FN | Precision | Recall | F1 | FPR | AP | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 7 | 8,190 | 33,123 | 6 | 0.000853970965 | 0.538461538 | 0.00170523752 | 0.198242684 | 0.088402682 | 9/13 |
| Isolation Forest | 12 | 27,163 | 14,150 | 1 | 0.000441582337 | 0.923076923 | 0.000882742386 | 0.657492799 | 0.080031605 | 13/13 |
| Local Outlier Factor | 10 | 10,060 | 31,253 | 3 | 0.000993048659 | 0.769230769 | 0.00198353665 | 0.243506886 | 0.0070649551 | 13/13 |
| Fixed schedule | 7 | 4,328 | 36,985 | 6 | 0.00161476355 | 0.538461538 | 0.00321987121 | 0.104761213 | 0.00209174054 | 10/13 |
| ADWIN + persistence | 7 | 11,404 | 29,909 | 6 | 0.000613443169 | 0.538461538 | 0.0012254902 | 0.276039019 | 0.00260020512 | 9/13 |
| Full selective policy | 8 | 19,478 | 21,835 | 5 | 0.000410551165 | 0.615384615 | 0.0008205549 | 0.47147387 | 0.0775222319 | 10/13 |

## Table F. Update efficiency

Primary synthetic holdout. Unmatched refits fall outside the protocol matching rule or lack an available event. Delay is the median matched onset-to-refit delay. [CSV](tables/table_f.csv)

| Policy | Refits | Refit-input uses | Matched refits | Unmatched refits | Median delay |
| --- | --- | --- | --- | --- | --- |
| Static Z-score | 0 | 0 | 0 | 0 | — |
| Fixed schedule | 15,000 | 3,840,000 | 1,280 | 13,720 | 255 |
| Immediate ADWIN | 1,534 | 392,704 | 1,280 | 254 | 63 |
| ADWIN + persistence | 1,430 | 187,584 | 1,280 | 150 | 191 |
| Full selective policy | 1,326 | 225,242 | 1,280 | 46 | 287 |
| Persistence + filtering | 1,482 | 253,001 | 1,280 | 202 | 287 |

## Table G. Single-host local Spark benchmark

Development workloads on Spark local[2]. Arrival and committed rates are records/s. Latency is publish-to-commit p95 in seconds. Full precision and raw memory units are preserved in the CSV. [CSV](tables/table_g.csv)

| Streams | Target | Observed arrival | Committed | Interval s | Commit p95 s | Peak backlog | Peak RSS bytes | SQLite bytes | Refits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 512 | 445.790276 | 213.404219 | 0.5 | 2.40598473 | 896 | 679,575,552 | 356,352 | 1 |
| 1 | 2048 | 1755.02323 | 951.667422 | 0.25 | 0.440705098 | 896 | 720,240,640 | 360,448 | 1 |
| 4 | 512 | 511.843877 | 485.193467 | 0.5 | 0.496995543 | 256 | 807,858,176 | 1,363,968 | 4 |
| 4 | 2048 | 2042.3962 | 1793.42735 | 0.25 | 0.327768589 | 1,024 | 841,879,552 | 1,368,064 | 4 |
| 8 | 512 | 511.895145 | 504.621372 | 0.5 | 0.318312316 | 256 | 902,221,824 | 2,707,456 | 8 |
| 8 | 2048 | 2045.80532 | 1803.54023 | 0.25 | 0.539152136 | 1,024 | 886,599,680 | 2,703,360 | 8 |
| 8 | 4096 | 4086.96316 | 3885.98461 | 0.25 | 0.49854186 | 3,072 | 984,715,264 | 12,169,216 | 8 |
| 8 | 8192 | 8175.81388 | 3303.65242 | 0.1 | 5.79424742 | 21,300 | 1,000,787,968 | 12,144,640 | 8 |
