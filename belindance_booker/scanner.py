import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .scraper import Scraper
from .exceptions import InvalidWodBusterResponse


@dataclass
class PrivateClass:
    date: datetime.date
    time: str
    class_id: int
    epoch: int
    spots_left: int


def find_private_classes(scraper: Scraper, class_name: str) -> list[PrivateClass]:
    today = datetime.date.today()
    last_day = _last_day_of_month(today)
    dates = [today + datetime.timedelta(days=i) for i in range((last_day - today).days + 1)]

    results: list[PrivateClass] = []

    def scan_date(date: datetime.date) -> list[PrivateClass]:
        try:
            data, epoch = scraper.get_classes(date)
        except InvalidWodBusterResponse as e:
            logging.warning("Failed to fetch classes for %s: %s", date, e)
            return []

        if not data.get("Data"):
            return []

        found = []
        for entry in data["Data"]:
            for valor in entry.get("Valores", []):
                val = valor.get("Valor", {})
                name = _extract_class_name(val)
                if name and class_name.upper() in name.upper():
                    status = valor.get("TipoEstado", "")
                    if status == "Borrable":
                        logging.info("Already booked: %s on %s", name, date)
                        continue
                    athletes = val.get("AtletasEntrenando", [])
                    spots = val.get("Plazas", 0)
                    if len(athletes) >= spots:
                        logging.info("Class full: %s on %s", name, date)
                        continue
                    found.append(PrivateClass(
                        date=date,
                        time=entry.get("Hora", ""),
                        class_id=val["Id"],
                        epoch=epoch,
                        spots_left=spots - len(athletes),
                    ))
        return found

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(scan_date, d): d for d in dates}
        for future in as_completed(futures):
            results.extend(future.result())

    results.sort(key=lambda c: (c.date, c.time))
    return results


def _extract_class_name(val: dict) -> str:
    for field in ("Nombre", "Titulo", "Descripcion", "Actividad", "NombreActividad", "Name"):
        if field in val:
            return str(val[field])
    return ""


def _last_day_of_month(date: datetime.date) -> datetime.date:
    if date.month == 12:
        return datetime.date(date.year, 12, 31)
    return datetime.date(date.year, date.month + 1, 1) - datetime.timedelta(days=1)
