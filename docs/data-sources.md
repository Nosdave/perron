# Data sources

| Data | Source | Interval | Notes |
|---|---|---|---|
| STIB/MIVB real-time departures | Belgian Mobility open data, `rt/WaitingTimes` | 30 s (60 s without key) | all configured stops in one request |
| STIB disruptions | Belgian Mobility, `rt/TravellersInformation` | 10 min | filtered to configured lines and stops |
| SNCB/NMBS departures | [iRail](https://api.irail.be) liveboard | 60 s | no key; 3 requests/s limit |
| Public-transport commute | iRail connections | 5 min | |
| Weather, radar nowcast, warnings | RMI/KMI app API (`getForecasts`) | 15 min | unofficial endpoint used by the RMI app; may change |
| BE-Alert | publicalerts.be CapGateway feed | 5 min | alerts are matched against the configured location |
| Headlines (optional) | Brussels Times WordPress API | 30 min | |
| Stop and station lists (setup helper) | STIB official GTFS, iRail stations | build time | `tools/gen_site_data.py` |
| Line colours | STIB and SNCB official GTFS (`routes.txt`) | build time | `tools/gen_assets.py` |

## API keys and rate limits

The STIB endpoints answer without a key, but anonymous access shares a small quota per public IP
address. A free personal key from the Belgian Mobility open-data portal is recommended. Run only
**one** STIB consumer per household — Home Assistant can read the board's sensors instead of
polling the API itself.

## Attribution and licences

Transit and weather data remain the property of their providers (STIB-MIVB/Belgian Mobility,
SNCB/NMBS via iRail, the Royal Meteorological Institute of Belgium, the Belgian National Crisis
Centre) and are used under their respective open-data terms. Perron is not affiliated with or
endorsed by any of them. Bitmap fonts: X11 misc-fixed (public domain).
