import click
import httpx
import math
import sys
import pandas as pd
from functools import partial


def p_get_gauge_fun(
    p_server: str, fun: str, gauge: str, node: str, end: str, duration: str
):
    params = {
        "query": f'{fun}({gauge}{{instance="{node}:9100"}}[{duration}s])',
        "time": end,
    }
    res = httpx.get(f"http://{p_server}:9090/api/v1/query", params=params)
    if res.status_code != 200:
        print("Error while fetching data")
        print("Request url: ", res.url)
        sys.exit()
    else:
        return res.json()["data"]["result"][0]["value"][1]


def get_load1(row: pd.DataFrame, p_server: str):
    node = row["node"]  # type: ignore
    t_td = row["time_transcoding_done"].isoformat()  # type: ignore
    duration = str(math.ceil(row["timediff_transcoding_done"].total_seconds()))  # type: ignore

    res = tuple(
        p_get_gauge_fun(
            p_server=p_server,
            fun=f,
            gauge="node_load1",
            node=node,  # type: ignore
            end=t_td,
            duration=duration,
        )
        for f in ["min_over_time", "avg_over_time", "max_over_time"]
    )

    return res


@click.command()
@click.argument("input_csv_filename", type=click.Path(exists=True))
@click.option(
    "-s",
    "--prometheus-server",
    default="controller",
    help="The hostname or IP address of the Prometheus server",
)
def process_csv_file(input_csv_filename: click.Path, prometheus_server: str):
    ok_logs_csv_path = input_csv_filename
    workers_csv_path = str(input_csv_filename).replace("ok-requests.csv", "workers.csv")
    print(f"Processing csv files: {input_csv_filename}, {workers_csv_path}")
    date_cols = [
        "time_received",
        "time_assigned",
        "time_started",
        "time_file_downloaded",
        "time_transcoding_done",
        "time_file_uploaded",
    ]
    timedelta_cols = [
        "timediff_assigned",
        "timediff_started",
        "timediff_file_downloaded",
        "timediff_transcoding_done",
        "timediff_file_uploaded",
    ]
    converters = {name: pd.to_timedelta for name in timedelta_cols}
    req = pd.read_csv(
        input_csv_filename,  # type: ignore
        parse_dates=date_cols,
        converters=converters,  # type: ignore
    )
    w_date_cols = ["time_registered", "time_created", "time_destroyed"]
    w_timedelta_cols = ["timediff_registered", "timediff_destroyed"]
    w_converters = {name: pd.to_timedelta for name in w_timedelta_cols}
    workers = pd.read_csv(
        workers_csv_path,  # type: ignore
        parse_dates=w_date_cols,
        converters=w_converters,  # type: ignore
    )

    # Add the name of the worker and the node hosting it by joining the req
    # dataframe with the worker dataframe.
    req_w = pd.merge(
        req, workers[["worker_id", "name", "node"]], on="worker_id", how="left"
    )

    # Add three columns with the node_load1 min, avg, max
    req_w[["load1_mean", "load1_avg", "load1_max"]] = req_w.apply(
        partial(get_load1, p_server=prometheus_server),
        axis=1,
        result_type="expand",
    )

    req_w.to_csv(
        str(input_csv_filename).replace(
            "ok-requests.csv", "ok-requests-node-stats.csv"
        ),
        index=False,
    )


if __name__ == "__main__":
    process_csv_file()
