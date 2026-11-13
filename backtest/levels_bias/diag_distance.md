# Diagnostic (not pre-registered): reversal rate by distance-from-price bin (ATR units), strong+medium

|                                               |   size_control |   size_level |   mean_control |   mean_level |   diff_pp |
|:----------------------------------------------|---------------:|-------------:|---------------:|-------------:|----------:|
| ('IS', Interval(0.3, 1.0, closed='right'))    |            333 |         1546 |          0.628 |        0.606 |    -2.155 |
| ('IS', Interval(1.0, 2.0, closed='right'))    |           1509 |         1888 |          0.695 |        0.699 |     0.399 |
| ('IS', Interval(2.0, 4.0, closed='right'))    |           2445 |         2784 |          0.738 |        0.735 |    -0.328 |
| ('IS', Interval(4.0, 8.0, closed='right'))    |           2317 |         2521 |          0.768 |        0.762 |    -0.663 |
| ('IS', Interval(8.0, 100.0, closed='right'))  |           1150 |         1197 |          0.824 |        0.831 |     0.69  |
| ('OOS', Interval(0.3, 1.0, closed='right'))   |            698 |         1773 |          0.622 |        0.584 |    -3.746 |
| ('OOS', Interval(1.0, 2.0, closed='right'))   |           1446 |         1981 |          0.645 |        0.655 |     0.949 |
| ('OOS', Interval(2.0, 4.0, closed='right'))   |           2228 |         2619 |          0.682 |        0.705 |     2.3   |
| ('OOS', Interval(4.0, 8.0, closed='right'))   |           1737 |         2043 |          0.736 |        0.743 |     0.67  |
| ('OOS', Interval(8.0, 100.0, closed='right')) |            674 |          768 |          0.782 |        0.772 |    -0.976 |