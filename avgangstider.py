from string import Template
import textwrap
import requests
import json
import arrow
import time
import subprocess
import sys
import re

from dotenv import dotenv_values
config = dotenv_values(".env")


stoppesteder={}
try:
    with open("stoppesteder.txt", "r", encoding="utf-8") as f:
        for linje in f:
            linje = linje.strip()
            
            # Hopper over tomme linjer, kommentarer eller linjer uten likhetstegn
            if not linje or linje.startswith("#") or "=" not in linje:
                continue
            
            # Splitter kun på det FØRSTE likhetstegnet
            navn, nsr_id = linje.split("=", 1)
            
            # Vasker bort unødvendige mellomrom og doble/enkle fnutter hvis de finnes
            ren_navn = navn.strip().strip('"').strip("'")
            ren_id = nsr_id.strip().strip('"').strip("'")
            
            stoppesteder[ren_navn] = ren_id
except FileNotFoundError:
    print("Du må opprette filen stoppesteder.txt og legge stoppestedne der.")
    print("Se på stoppesteder_eksempel.txt hvordan filen skal se ut")
    print("Du kan finne stoppesteder på stoppesteder.entur.org")
    sys.exit(1)

nycthemeron = 24*3600 # et døgn
hour = 3600

class TermStil:
    MODERNE = "moderne"
    FANCY = "fancy"
    KLASSISK = "klassisk"
TERM_MODE=TermStil.MODERNE


def minutter_til_avgang(expected_iso_str: str) -> str:
    """Regner ut hvor mange minutter det er til bussen kommer, basert på sanntid."""
    # 1. Hent tidspunktet for når bussen forventes å dra
    forventet_tid = arrow.get(expected_iso_str)
    
    # 2. Hent klokkeslettet akkurat nå (inkludert riktig tidssone)
    naa = arrow.now(forventet_tid.tzinfo)
    
    # 3. Regn ut forskjellen i sekunder og gjør om til minutter
    differanse_sekunder = (forventet_tid - naa).total_seconds()
    minutter_igjen = int(differanse_sekunder // 60)
    
    # 4. Returner en menneskevennlig tekst basert på hvor nær bussen er
    if minutter_igjen <= 0:
        return "Nå"
    elif minutter_igjen == 1:
        return "1 min"
    else:
        return f"{minutter_igjen} min"

def formater_forsinkelse_moderne(forsinkelse_minutter: str) -> str:
    if forsinkelse_minutter > 0:
        return f"🔴 {forsinkelse_minutter} min forsinket"
    elif forsinkelse_minutter < 0:
        # Hvis bussen mirakuløst ligger *foran* skjema
        return f"💚 {abs(forsinkelse_minutter)} min tidlig"
    else:
        return "💚 I rute"


def formater_forsinkelse_klassisk(forsinkelse_minutter: str) -> str:

    # ANSI-fargekoder (Standard for terminaler)
    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m" # Nullstiller fargen så ikke resten av tabellen blir farget


    if forsinkelse_minutter > 0:
        # Farger teksten rød, og legger til en tydelig [!] eller [X] i stedet for emoji
        return f"{RED}[!] {forsinkelse_minutter} min forsinket{RESET}"
    elif forsinkelse_minutter < 0:
        # Knallgrønn tekst for det tromsøværske miraklet
        return f"{GREEN}[+] {abs(forsinkelse_minutter)} min tidlig{RESET}"
    else:
        # Knallgrønn og synlig "I rute"
        return f"{GREEN}[V] I rute{RESET}"

def formater_forsinkelse(aimed_raw: str, expected_raw: str) -> str:
    # 1. Parse ISO-strengene fra Entur til Arrow-objekter
    aimed = arrow.get(aimed_raw)
    expected = arrow.get(expected_raw)
    
    # 2. Regn ut forskjellen i sekunder
    # (expected minus aimed gir oss hvor mye *mer* tid bussen bruker)
    tidsdifferanse = (expected - aimed).total_seconds()
    
    # 3. Gjør om til hele minutter
    forsinkelse_minutter = int(tidsdifferanse // 60)

    match TERM_MODE:
        case TermStil.MODERNE:
            ret_text = formater_forsinkelse_moderne(forsinkelse_minutter)
        case _:
            ret_text = formater_forsinkelse_klassisk(forsinkelse_minutter) 

    return ret_text


def iso_til_normaltid(time: str, format="HH:mm") -> str:
    return arrow.get(time).format(format)

################## Departure board for a stop place
#
# This query fetches upcoming departures from a specific stop place,
# similar to what you would see on a departure board at a station.
#
# Key parameters:
# - id: The NSR ID of the stop place (e.g., "NSR:StopPlace:548" for Stavanger stadion)
# - timeRange: How far ahead to look for departures (in seconds, 72100 = ~20 hours)
# - numberOfDepartures: Maximum number of departures to return
#
# The response includes both scheduled (aimed) and real-time (expected/actual) times,
# allowing you to show delays. The 'realtime' field indicates if real-time data
# is available for that departure.
#
# Use case: Building a departure board display, showing upcoming departures
# from a specific stop with real-time updates.
#


def construct_stop_place_table_query_body(nsr_stop_place_id: str, time_range=3600):
    raw_template = """
    {
      stopPlace(id: "$nsr_id") {
        id
        name
        estimatedCalls(timeRange: $time_range, numberOfDepartures: 10) {     
          realtime
          aimedArrivalTime
          aimedDepartureTime
          expectedArrivalTime
          expectedDepartureTime
          actualArrivalTime
          actualDepartureTime
          date
          forBoarding
          forAlighting
          destinationDisplay {
            frontText
          }
          quay {
            id
          }
          serviceJourney {
            journeyPattern {
              line {
                id
                name
                publicCode
                transportMode
              }
            }
          }
        }
      }
    }
    """
    query_template = Template(textwrap.dedent(raw_template).strip())
    query = query_template.substitute(nsr_id=nsr_stop_place_id, time_range=time_range)
    return query


def debug_and_send_stop_place_query(query: str, debug=False):
    session = requests.Session()
    url = "https://api.entur.io/journey-planner/v3/graphql"
    body = {"query": query}
    headers = {"ET-Client-Name": f"{config['etClientName']}"}

    # 1. Opprett og klargjør forespørselen (viktig: bruk json= for GraphQL)
    req = requests.Request(method="POST", url=url, headers=headers, json=body)
    prepared = session.prepare_request(req)

    response = session.send(prepared)
    return response.json()


def hent_avgangsinfo(stoppesteder: dict):
    responsedict = {}

    for stoppested, nsr_id in stoppesteder.items():
        graphql_query = construct_stop_place_table_query_body(nsr_id, time_range=1800)
        response = debug_and_send_stop_place_query(graphql_query)
        responsedict[stoppested] = response
        api_stoppested_navn = response['data']['stopPlace']['name']
        if api_stoppested_navn != stoppested:
            print(f"fikk feil stoppested! -- fikk: {api_stoppested_navn} -- forventet: {stoppested}")
    return responsedict

total_bredde = 95

command = 'cls' if sys.platform.startswith('win') else 'clear'
subprocess.run([command], check=True)

while True:
    
    # ==============================================================================
    # TØM TERMINALEN (TUI-EFFEKT)
    # ==============================================================================
    # 'cls' brukes på Windows, 'clear' på Linux/macOS
    # Sjekker om systemet er Windows ('nt'), velger 'cls', ellers 'clear'
    print("henter avgangsinfo...")
    avgangsinfo = hent_avgangsinfo(stoppesteder)
    command = 'cls' if sys.platform.startswith('win') else 'clear'
    subprocess.run([command], check=True)

    for response in avgangsinfo.values():

        api_stoppested_navn = response['data']['stopPlace']['name']
        estimated_calls = response['data']['stopPlace']['estimatedCalls']
        if not estimated_calls: continue
        print(f"{f' {api_stoppested_navn} ':-^{total_bredde}}📍")
        for call in estimated_calls:
            # f.eks 28-linjen i Tromsø er på formatet "TRO:Line:1_28". Fisker ut linjenummeret 28.
            # funksjonen finn_linjenummer fjerner uuid hvis en buss ikke har sanntidsdata
            linje_nr = call["serviceJourney"]["journeyPattern"]["line"].get("publicCode")
            if not linje_nr:
                "Ukjent"


            tid_til_forventet_avgang = minutter_til_avgang(call['expectedDepartureTime']) # f.eks. "5 min" eller "Nå"

            destinasjon = call["destinationDisplay"]["frontText"] # F.eks "Solligården via sentrum"

            planlagt_avgang_iso = call['aimedDepartureTime']
            forvented_avgang_iso = call['expectedDepartureTime']
            forsinkelse = formater_forsinkelse(planlagt_avgang_iso, forvented_avgang_iso)
            planlagt_avgang = iso_til_normaltid(planlagt_avgang_iso)
            forvented_avgang = iso_til_normaltid(forvented_avgang_iso)

            if call['realtime']:
                print(f"linje: {linje_nr:4}: {destinasjon:35}  {tid_til_forventet_avgang:6}  {forvented_avgang} ({planlagt_avgang}) -- {forsinkelse:18}")
            else:
                tid_til_planlagt_avgang = minutter_til_avgang(call['aimedDepartureTime']) # f.eks. "5 min" eller "Nå"
                print(f"linje: {linje_nr:4}: {destinasjon:35}  {tid_til_forventet_avgang:6}  {planlagt_avgang} -- mangler sanntidsdata")
    print("="*(total_bredde + 1))
    time.sleep(60)
