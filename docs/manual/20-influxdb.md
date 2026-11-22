# 20. InfluxDB and Grafana

The **Data** control (chapter 6) logs to a SQLite file beside the form: perfect for
a scale's tickets or a day's readings you open in Excel. When you want weeks of
readings on graphs, alongside your other equipment, the usual answer is
**InfluxDB** for the data and **Grafana** for the dashboards. The **InfluxDB**
control sends your panel's values there with no code.

It works with InfluxDB 2.x (self-hosted or InfluxDB Cloud), needs nothing extra
installed, and copes with InfluxDB being away: points wait in memory and go when
it comes back.

## Before you start: a bucket and a token

In the InfluxDB web page (usually `http://yourserver:8086`):

1. **Load Data → Buckets → Create Bucket**. Call it `panelworks` (or anything) and
   choose how long to keep the data.
2. **Load Data → API Tokens → Generate API Token → Custom API Token**. Give it
   **Write** on that bucket (and **Read** if your code will use Query). Copy the
   token: InfluxDB shows it only once.
3. Note your **organization** name (top left, or your user menu).

Keep the token out of the form file. Put the settings in environment variables
instead, once, on the computer that runs the panel:

```
setx INFLUX_URL "http://192.168.1.20:8086"
setx INFLUX_ORG "homestead"
setx INFLUX_BUCKET "panelworks"
setx INFLUX_TOKEN "paste-the-token-here"
```

(On Linux or macOS, `export INFLUX_TOKEN=...` in `~/.profile`.) `setx` affects
windows opened afterwards, so close and reopen the command prompt or the designer.
The control's properties start as `${INFLUX_URL:-http://localhost:8086}`,
`${INFLUX_ORG}`, `${INFLUX_BUCKET:-panelworks}` and `${INFLUX_TOKEN}`, so these
are picked up without touching the form. You can type real values into the
properties instead, but then the token is in the `.json` you might share.

## Logging with no code

1. Add an **InfluxDB** control from the toolbox. It goes in the tray as `Influx1`.
2. Set **LogFields**, one per line, `field = Control.Property`, as on the Data control:

   ```
   volts = gauVolts.Value
   amps = gauAmps.Value
   pump = chkPump.Value
   state = lblState.Caption
   ```

3. Set **LogEvery** to how often, in seconds (10 is plenty for most panels).
4. Optional: **Tags**, one per line, for things you'll filter or group by in Grafana:

   ```
   site = barn
   panel = battery
   ```

Run it. Every 10 seconds a point goes into the bucket, with the measurement named
after the form (set **Measurement** to change it), your tags, and one field per
LogFields line. Points are collected and written together every **FlushEvery**
seconds (5), so a fast LogEvery doesn't mean a web request every second.

Numbers are always written as decimals, even when a value happens to be whole,
because InfluxDB refuses a field that is `52` (an integer) one minute and `52.5` (a
float) the next. Text that looks like a number (a Label's `"48.7"`) goes as a number;
True/False as booleans; anything else as text.

## Fields or tags?

**Fields** are the readings: volts, amps, level, temperature. **Tags** describe
where they came from: site, building, pump number. Grafana filters and groups by
tags, and InfluxDB indexes them, so keep tags to a few values that don't change
(a site name, not a timestamp or a reading). One panel watching three pumps could
log each with its own tag:

```python
def tmrLog_Timer(f):
    for i in range(3):
        f.Influx1.Log({"amps": f.gauAmps(i).Value, "running": f.chkRun(i).Value},
                      measurement="pump", tags={"pump": str(i + 1)})
```

## Logging from code

```python
f.Influx1.Log()                                  # the LogFields, now
f.Influx1.Log({"weight": 1234.5, "ticket": "A17"})                 # your own fields
f.Influx1.Log({"kwh": total}, measurement="energy", tags={"meter": "main"})
f.Influx1.Flush()                                # write now and wait (True if it went)
```

Log returns at once; the writing happens on its own thread, so a slow network
never freezes the panel. A Data control and an InfluxDB control can log the same
values side by side: a local copy for Excel and a long history for Grafana.

## When InfluxDB is away

If a write fails (the server is restarting, the Wi-Fi dropped), the points stay in
memory and are retried, waiting a little longer each time up to a minute. When it
answers again, everything waiting is written in order, so the graph has no gap.

- **Pending** says how many points are waiting.
- **MaxBuffer** (10,000) is how many it keeps. Past that the oldest are dropped and
  counted in **Dropped**. At LogEvery 10 that's more than a day.
- **Error(message)** fires once when writes start failing (not on every retry), and
  **Disconnected** with it; **Connected** fires when they work again.
- Closing the panel makes one last attempt to write what's waiting.

```python
def Influx1_Error(f, message):
    f.lblInflux.Caption = "InfluxDB: " + message
    f.shpInflux.FillColor = "red"

def Influx1_Written(f, count):
    f.shpInflux.FillColor = "lime green"
    f.lblInflux.Caption = f"InfluxDB: {f.Influx1.Written} points written"
```

## Graphing it in Grafana

1. In Grafana, **Connections → Data sources → Add data source → InfluxDB**.
2. Set **Query language** to **Flux**, the **URL** to your InfluxDB, and under
   InfluxDB Details your **Organization**, a **Token** with Read on the bucket, and the
   **Default Bucket**. Save & test.
3. Make a dashboard panel with this query (change the bucket and measurement):

   ```
   from(bucket: "panelworks")
     |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
     |> filter(fn: (r) => r._measurement == "BatteryPanel")
     |> filter(fn: (r) => r._field == "volts" or r._field == "amps")
     |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
   ```

The measurement is the form's name (the `name` at the top of the `.json`) unless
you set Measurement.

## Reading it back: Query

Query runs a Flux query and gives you the rows as a list of dicts, so a panel can
show yesterday's figures:

```python
def cmdYesterday_Click(f):
    rows = f.Influx1.Query('''
        from(bucket: "panelworks")
          |> range(start: -1d)
          |> filter(fn: (r) => r._field == "kwh")
          |> sum()''')
    f.lblYesterday.Caption = f"{rows[0]['_value']:.1f} kWh" if rows else "no data"
```

Each row has `_time`, `_value`, `_field`, `_measurement` and your tags. Query waits
for the answer, so use it from a button or Form_Load, not a fast Timer. It needs a
token with Read on the bucket.

## When it doesn't work

LastError holds the last problem; the Immediate window (Ctrl+G) shows it with
`? f.Influx1.LastError`.

| Message | What to check |
|---|---|
| `Org, Token not set` | The environment variables aren't set in this window: `setx` needs a new window |
| `can't reach http://...` | The URL and port (8086), and that InfluxDB is running; `f.Influx1.Ping()` |
| `HTTP 401` | The token is wrong, or was deleted |
| `HTTP 403` | The token can't write to that bucket: give it Write |
| `HTTP 404 ... not found` | The Org or Bucket name: they're case-sensitive |
| `HTTP 422 field type conflict` | The same field was written as text and as a number (or by another program as an integer): log it under a new field name |
| Points but nothing in Grafana | The time range, the measurement name (the form's name), and that the Grafana data source uses Flux |

InfluxDB 1.x speaks a different API (a database and a username instead of an org,
bucket and token), except **1.8**, which also accepts these 2.x writes: set Bucket to
`database/autogen` (database/retention policy), Org to anything, and Token to
`username:password` (anything at all if authentication is off).
