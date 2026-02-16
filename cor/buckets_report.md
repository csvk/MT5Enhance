# FX Pair Correlation Buckets

## Original 5 Buckets
Pairs grouped into 5 buckets to minimize intra-bucket absolute correlation (Daily).

### Bucket 1

| | AUDCHF | NZDCAD | GBPJPY | AUDNZD | EURJPY | NZDUSD |
|---|---|---|---|---|---|---|
| AUDCHF | 100 | 45.3 | <span style="color:red">**76.2**</span> | 52.7 | 61.6 | 61.2 |
| NZDCAD | 45.3 | 100 | 11.9 | -29.1 | -1.3 | 51.4 |
| GBPJPY | <span style="color:red">**76.2**</span> | 11.9 | 100 | 61.1 | <span style="color:red">**95.9**</span> | 64.0 |
| AUDNZD | 52.7 | -29.1 | 61.1 | 100 | 51.5 | -3.8 |
| EURJPY | 61.6 | -1.3 | <span style="color:red">**95.9**</span> | 51.5 | 100 | 62.2 |
| NZDUSD | 61.2 | 51.4 | 64.0 | -3.8 | 62.2 | 100 |

### Bucket 2

| | AUDUSD | CADCHF | GBPNZD | AUDJPY | USDCHF |
|---|---|---|---|---|---|
| AUDUSD | 100 | 59.8 | 2.2 | <span style="color:red">**91.7**</span> | -59.1 |
| CADCHF | 59.8 | 100 | -28.3 | 56.7 | 0.4 |
| GBPNZD | 2.2 | -28.3 | 100 | 25.1 | -2.9 |
| AUDJPY | <span style="color:red">**91.7**</span> | 56.7 | 25.1 | 100 | -39.4 |
| USDCHF | -59.1 | 0.4 | -2.9 | -39.4 | 100 |

### Bucket 3

| | EURCHF | GBPCHF | GBPUSD | GBPAUD | CADJPY | GBPCAD |
|---|---|---|---|---|---|---|
| EURCHF | 100 | 63.5 | 9.9 | -14.3 | 11.2 | 1.9 |
| GBPCHF | 63.5 | 100 | <span style="color:red">**67.7**</span> | -53.2 | 64.5 | 57.2 |
| GBPUSD | 9.9 | <span style="color:red">**67.7**</span> | 100 | -45.8 | <span style="color:red">**86.0**</span> | 35.0 |
| GBPAUD | -14.3 | -53.2 | -45.8 | 100 | -49.6 | -25.3 |
| CADJPY | 11.2 | 64.5 | <span style="color:red">**86.0**</span> | -49.6 | 100 | 18.8 |
| GBPCAD | 1.9 | 57.2 | 35.0 | -25.3 | 18.8 | 100 |

### Bucket 4

| | NZDJPY | EURNZD | USDCAD | AUDCAD | USDJPY |
|---|---|---|---|---|---|
| NZDJPY | 100 | <span style="color:red">**-79.5**</span> | <span style="color:red">**-78.6**</span> | 58.3 | 48.6 |
| EURNZD | <span style="color:red">**-79.5**</span> | 100 | 58.8 | -53.6 | -7.8 |
| USDCAD | <span style="color:red">**-78.6**</span> | 58.8 | 100 | -15.1 | -1.7 |
| AUDCAD | 58.3 | -53.6 | -15.1 | 100 | 53.2 |
| USDJPY | 48.6 | -7.8 | -1.7 | 53.2 | 100 |

### Bucket 5

| | NZDCHF | EURGBP | EURCAD | EURUSD | CHFJPY | EURAUD |
|---|---|---|---|---|---|---|
| NZDCHF | 100 | -52.5 | -51.7 | 36.1 | 0.4 | -57.5 |
| EURGBP | -52.5 | 100 | 60.4 | -37.3 | -63.6 | <span style="color:red">**92.2**</span> |
| EURCAD | -51.7 | 60.4 | 100 | -62.5 | -57.5 | 64.9 |
| EURUSD | 36.1 | -37.3 | -62.5 | 100 | 59.2 | -33.7 |
| CHFJPY | 0.4 | -63.6 | -57.5 | 59.2 | 100 | -57.3 |
| EURAUD | -57.5 | <span style="color:red">**92.2**</span> | 64.9 | -33.7 | -57.3 | 100 |

## Super Buckets
Two super buckets created by merging original buckets to minimize high correlations.

### Super Bucket 1 (Merged from Original Buckets: 1, 2)

Total High Correlations (abs >= 65): 14

| | AUDCHF | NZDCAD | GBPJPY | AUDNZD | EURJPY | NZDUSD | AUDUSD | CADCHF | GBPNZD | AUDJPY | USDCHF |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AUDCHF | 100 | 45.3 | <span style="color:red">**76.2**</span> | 52.7 | 61.6 | 61.2 | <span style="color:red">**80.8**</span> | <span style="color:red">**74.2**</span> | 0.4 | <span style="color:red">**84.8**</span> | -0.2 |
| NZDCAD | 45.3 | 100 | 11.9 | -29.1 | -1.3 | 51.4 | 30.2 | 22.4 | -61.3 | 18.3 | 10.4 |
| GBPJPY | <span style="color:red">**76.2**</span> | 11.9 | 100 | 61.1 | <span style="color:red">**95.9**</span> | 64.0 | <span style="color:red">**87.6**</span> | 53.6 | 32.7 | <span style="color:red">**97.4**</span> | -44.0 |
| AUDNZD | 52.7 | -29.1 | 61.1 | 100 | 51.5 | -3.8 | 48.0 | 6.5 | <span style="color:red">**75.6**</span> | <span style="color:red">**66.6**</span> | -9.2 |
| EURJPY | 61.6 | -1.3 | <span style="color:red">**95.9**</span> | 51.5 | 100 | 62.2 | <span style="color:red">**81.0**</span> | 50.5 | 28.8 | <span style="color:red">**91.4**</span> | -52.8 |
| NZDUSD | 61.2 | 51.4 | 64.0 | -3.8 | 62.2 | 100 | <span style="color:red">**85.8**</span> | 64.3 | -41.8 | <span style="color:red">**65.5**</span> | -61.9 |
| AUDUSD | <span style="color:red">**80.8**</span> | 30.2 | <span style="color:red">**87.6**</span> | 48.0 | <span style="color:red">**81.0**</span> | <span style="color:red">**85.8**</span> | 100 | 59.8 | 2.2 | <span style="color:red">**91.7**</span> | -59.1 |
| CADCHF | <span style="color:red">**74.2**</span> | 22.4 | 53.6 | 6.5 | 50.5 | 64.3 | 59.8 | 100 | -28.3 | 56.7 | 0.4 |
| GBPNZD | 0.4 | -61.3 | 32.7 | <span style="color:red">**75.6**</span> | 28.8 | -41.8 | 2.2 | -28.3 | 100 | 25.1 | -2.9 |
| AUDJPY | <span style="color:red">**84.8**</span> | 18.3 | <span style="color:red">**97.4**</span> | <span style="color:red">**66.6**</span> | <span style="color:red">**91.4**</span> | <span style="color:red">**65.5**</span> | <span style="color:red">**91.7**</span> | 56.7 | 25.1 | 100 | -39.4 |
| USDCHF | -0.2 | 10.4 | -44.0 | -9.2 | -52.8 | -61.9 | -59.1 | 0.4 | -2.9 | -39.4 | 100 |

### Super Bucket 2 (Merged from Original Buckets: 2, 3)

Total High Correlations (abs >= 65): 14

| | AUDUSD | CADCHF | GBPNZD | AUDJPY | USDCHF | EURCHF | GBPCHF | GBPUSD | GBPAUD | CADJPY | GBPCAD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AUDUSD | 100 | 59.8 | 2.2 | <span style="color:red">**91.7**</span> | -59.1 | 12.8 | <span style="color:red">**72.2**</span> | <span style="color:red">**95.4**</span> | <span style="color:red">**-70.3**</span> | <span style="color:red">**85.5**</span> | 36.7 |
| CADCHF | 59.8 | 100 | -28.3 | 56.7 | 0.4 | <span style="color:red">**75.7**</span> | <span style="color:red">**77.7**</span> | 55.7 | -45.1 | 64.1 | -7.2 |
| GBPNZD | 2.2 | -28.3 | 100 | 25.1 | -2.9 | -40.5 | 5.6 | 6.2 | 8.9 | 19.3 | 45.6 |
| AUDJPY | <span style="color:red">**91.7**</span> | 56.7 | 25.1 | 100 | -39.4 | 12.4 | <span style="color:red">**77.8**</span> | <span style="color:red">**85.0**</span> | <span style="color:red">**-70.3**</span> | <span style="color:red">**91.7**</span> | 49.5 |
| USDCHF | -59.1 | 0.4 | -2.9 | -39.4 | 100 | 48.6 | 5.8 | <span style="color:red">**-69.5**</span> | 10.6 | -53.5 | 8.2 |
| EURCHF | 12.8 | <span style="color:red">**75.7**</span> | -40.5 | 12.4 | 48.6 | 100 | 63.5 | 9.9 | -14.3 | 11.2 | 1.9 |
| GBPCHF | <span style="color:red">**72.2**</span> | <span style="color:red">**77.7**</span> | 5.6 | <span style="color:red">**77.8**</span> | 5.8 | 63.5 | 100 | <span style="color:red">**67.7**</span> | -53.2 | 64.5 | 57.2 |
| GBPUSD | <span style="color:red">**95.4**</span> | 55.7 | 6.2 | <span style="color:red">**85.0**</span> | <span style="color:red">**-69.5**</span> | 9.9 | <span style="color:red">**67.7**</span> | 100 | -45.8 | <span style="color:red">**86.0**</span> | 35.0 |
| GBPAUD | <span style="color:red">**-70.3**</span> | -45.1 | 8.9 | <span style="color:red">**-70.3**</span> | 10.6 | -14.3 | -53.2 | -45.8 | 100 | -49.6 | -25.3 |
| CADJPY | <span style="color:red">**85.5**</span> | 64.1 | 19.3 | <span style="color:red">**91.7**</span> | -53.5 | 11.2 | 64.5 | <span style="color:red">**86.0**</span> | -49.6 | 100 | 18.8 |
| GBPCAD | 36.7 | -7.2 | 45.6 | 49.5 | 8.2 | 1.9 | 57.2 | 35.0 | -25.3 | 18.8 | 100 |

## Max Inclusion 3-Bucket Configuration
Three buckets maximizing the number of pairs included with at most 1 high correlation per bucket.

Total pairs included: 20 / 28

### Inclusion Bucket 1

| | NZDCHF | USDJPY | USDCHF | GBPNZD | AUDUSD | EURCAD | GBPCAD |
|---|---|---|---|---|---|---|---|
| NZDCHF | 100 | 8.0 | 6.7 | -55.6 | 58.7 | -51.7 | 20.0 |
| USDJPY | 8.0 | 100 | 17.0 | 55.7 | 30.8 | -29.7 | 48.6 |
| USDCHF | 6.7 | 17.0 | 100 | -2.9 | -59.1 | 43.5 | 8.2 |
| GBPNZD | -55.6 | 55.7 | -2.9 | 100 | 2.2 | 5.1 | 45.6 |
| AUDUSD | 58.7 | 30.8 | -59.1 | 2.2 | 100 | <span style="color:red">**-77.6**</span> | 36.7 |
| EURCAD | -51.7 | -29.7 | 43.5 | 5.1 | <span style="color:red">**-77.6**</span> | 100 | 12.3 |
| GBPCAD | 20.0 | 48.6 | 8.2 | 45.6 | 36.7 | 12.3 | 100 |

### Inclusion Bucket 2

| | CADCHF | GBPJPY | NZDCAD | EURUSD | NZDUSD | GBPAUD | AUDNZD |
|---|---|---|---|---|---|---|---|
| CADCHF | 100 | 53.6 | 22.4 | 42.4 | 64.3 | -45.1 | 6.5 |
| GBPJPY | 53.6 | 100 | 11.9 | 56.3 | 64.0 | -52.3 | 61.1 |
| NZDCAD | 22.4 | 11.9 | 100 | 12.3 | 51.4 | -31.4 | -29.1 |
| EURUSD | 42.4 | 56.3 | 12.3 | 100 | <span style="color:red">**86.9**</span> | -20.0 | -2.9 |
| NZDUSD | 64.3 | 64.0 | 51.4 | <span style="color:red">**86.9**</span> | 100 | -46.0 | -3.8 |
| GBPAUD | -45.1 | -52.3 | -31.4 | -20.0 | -46.0 | 100 | -58.4 |
| AUDNZD | 6.5 | 61.1 | -29.1 | -2.9 | -3.8 | -58.4 | 100 |

### Inclusion Bucket 3

| | EURCHF | USDCAD | CHFJPY | AUDCAD | EURNZD | EURGBP |
|---|---|---|---|---|---|---|
| EURCHF | 100 | -10.1 | -35.3 | 9.8 | -48.9 | -17.1 |
| USDCAD | -10.1 | 100 | -64.5 | -15.1 | 58.8 | 51.1 |
| CHFJPY | -35.3 | -64.5 | 100 | 39.6 | -21.4 | -63.6 |
| AUDCAD | 9.8 | -15.1 | 39.6 | 100 | -53.6 | <span style="color:red">**-82.4**</span> |
| EURNZD | -48.9 | 58.8 | -21.4 | -53.6 | 100 | 62.6 |
| EURGBP | -17.1 | 51.1 | -63.6 | <span style="color:red">**-82.4**</span> | 62.6 | 100 |

