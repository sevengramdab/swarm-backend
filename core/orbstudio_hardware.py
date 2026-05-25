"""
ORBSTUDIO SWARM — HARDWARE INTEGRATION LAYER v2.0
AGENTS: 04 (Power Grid), 05 (Hardware Deployer), 06 (Thermal Router),
        08 (Aqua-Biologist), 09 (Botanist), 10 (Fluid Dynamics), 11 (Filtration),
        12 (Telemetry), 16 (Sourcing), 17 (Build Analyst)

This is NOT a simulation. This is the real-world interface between software
and physical hardware — sensors, relays, pumps, heat exchangers, and compute.

v2.0 adds:
  - Multi-supplier sourcing per part (Chengdu local, Amazon, DigiKey, AliExpress, etc.)
  - Build profiles: Budget / Standard / Premium / Custom
  - Build analysis engine: cost, thermal, sourcing risk, ROI
  - Wiring schematic with proper box-drawing characters

Every component below references actual off-the-shelf parts with real specs,
part numbers, and pricing (as of 2026-05-22).

ANALOGY: This file is the electrical submittal package + the procurement
department + the engineering review board — all in one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any
import time
import json


# ═══════════════════════════════════════════════════════════════════════════
# SECTION A: SUPPLIER OPTIONS — MULTIPLE SOURCES PER PART
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SupplierOption:
    """One sourcing option for a BOM item."""
    supplier_name: str
    location: str                # e.g. "Chengdu, China", "Online - Global", "Shenzhen, China"
    unit_price_usd: float
    currency: str = "USD"
    url: str = ""                # Purchase URL
    shipping_days: int = 7       # Estimated shipping time
    min_order_qty: int = 1
    in_stock: bool = True
    notes: str = ""              # e.g. "Bulk discount at 50+", "Genuine only"
    reliability_score: float = 5.0  # 1-10, 10 = most reliable


@dataclass
class SourcedBOMItem:
    """One BOM line item with MULTIPLE supplier options."""
    part_number: str
    description: str
    category: str                # sensor, actuator, pump, heat_exchanger, controller, enclosure, power, misc
    qty: int
    datasheet_url: str
    notes: str = ""
    options: List[SupplierOption] = field(default_factory=list)

    def best_option(self, preference: str = "price") -> SupplierOption:
        """Return the best sourcing option based on preference."""
        if not self.options:
            return SupplierOption(supplier_name="N/A", location="N/A", unit_price_usd=0.0)
        if preference == "price":
            return min(self.options, key=lambda o: o.unit_price_usd)
        if preference == "speed":
            return min(self.options, key=lambda o: o.shipping_days)
        if preference == "reliability":
            return max(self.options, key=lambda o: o.reliability_score)
        return self.options[0]

    def to_dict(self, selected_option_idx: int = 0) -> dict:
        """Serialize with a selected option as the active choice."""
        opt = self.options[selected_option_idx] if self.options else None
        return {
            "part_number": self.part_number,
            "description": self.description,
            "category": self.category,
            "qty": self.qty,
            "datasheet_url": self.datasheet_url,
            "notes": self.notes,
            "options": [asdict(o) for o in self.options],
            "selected_option_idx": selected_option_idx,
            "selected_price_usd": opt.unit_price_usd if opt else 0.0,
            "selected_supplier": opt.supplier_name if opt else "N/A",
            "selected_location": opt.location if opt else "N/A",
            "selected_url": opt.url if opt else "",
            "extended_price_usd": (opt.unit_price_usd * self.qty) if opt else 0.0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION B: COMPLETE BOM WITH MULTI-SUPPLIER SOURCING
# ═══════════════════════════════════════════════════════════════════════════

# ── TEMPERATURE SENSORS ──
ITEM_DS18B20 = SourcedBOMItem(
    part_number="DS18B20",
    description="Waterproof Digital Temperature Sensor, 3m cable, stainless steel probe",
    category="sensor",
    qty=12,
    datasheet_url="https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf",
    notes="1-Wire protocol. Use 4.7kΩ pull-up on DATA line. One per tank + exhaust duct + HX inlet/outlet.",
    options=[
        SupplierOption("Amazon - AZDelivery", "Online - Global", 4.50, "USD", "https://www.amazon.com/s?k=DS18B20+waterproof+sensor+3m", 7, 1, True, "Prime shipping, 10-pack available", 9.0),
        SupplierOption("Taobao - Electronics Wholesale", "Online - China", 1.20, "USD", "", 5, 10, True, "10-pack waterproof probes. Most cost-effective.", 7.5),
        SupplierOption("1688.com - Shenzhen Sensor Wholesale", "Online - China", 0.85, "USD", "", 5, 50, True, "Factory direct. Buy 50pc for projects. Test accuracy.", 6.5),
        SupplierOption("Pinduoduo - Sensor Store", "Online - China", 0.70, "USD", "", 5, 5, True, "Cheapest option. May be clones. Test ±0.5°C accuracy.", 5.0),
        SupplierOption("JD.com - JD Electronics", "Online - China", 1.80, "USD", "", 2, 1, True, "JD official store. Genuine Maxim chips. Fast ship.", 8.5),
        SupplierOption("AliExpress - Keyes Store", "Online - China", 1.80, "USD", "https://www.aliexpress.com/wholesale?SearchText=DS18B20+waterproof+sensor", 21, 10, True, "Bulk pricing, 10pc min. Long shipping.", 7.0),
        SupplierOption("Chengdu - Chuanke Electronics", "Chengdu, China", 2.20, "USD", "", 1, 1, True, "Local pickup same day. Jincheng Plaza, Wuhou District.", 8.0),
        SupplierOption("Digi-Key", "Online - Global", 5.80, "USD", "https://www.digikey.com/en/products/result?keywords=DS18B20", 5, 1, True, "Genuine Maxim parts. Fastest shipping.", 10.0),
        SupplierOption("Taobao - LCSC Mall", "Online - China", 1.50, "USD", "https://www.lcsc.com/search?q=DS18B20", 3, 5, True, "LCSC/JLCPCB ecosystem. Good for recurring orders.", 8.5),
    ]
)

ITEM_DHT22 = SourcedBOMItem(
    part_number="DHT22 / AM2302",
    description="Digital Temperature & Humidity Sensor",
    category="sensor",
    qty=4,
    datasheet_url="https://www.adafruit.com/product/385",
    notes="Ambient air monitoring in grow beds and server room. Not waterproof.",
    options=[
        SupplierOption("Amazon - Adafruit", "Online - Global", 9.95, "USD", "https://www.amazon.com/s?k=DHT22+AM2302+temperature+humidity+sensor", 5, 1, True, "Genuine Adafruit, best accuracy", 9.5),
        SupplierOption("Taobao - Sensor House", "Online - China", 2.50, "USD", "", 5, 1, True, "Aosong genuine DHT22. Includes PCB module.", 7.5),
        SupplierOption("1688.com - Temp/Humidity Sensor Wholesale", "Online - China", 1.80, "USD", "", 5, 10, True, "Bulk Aosong modules. Verify chip markings.", 6.5),
        SupplierOption("Pinduoduo - Electronics Store", "Online - China", 1.20, "USD", "", 5, 1, True, "Very cheap. Many fakes. Test humidity accuracy.", 4.5),
        SupplierOption("JD.com - JD Sensors", "Online - China", 3.00, "USD", "", 2, 1, True, "JD official store. Genuine parts. Fast shipping.", 8.0),
        SupplierOption("AliExpress - Sensor Kit Store", "Online - China", 3.20, "USD", "https://www.aliexpress.com/wholesale?SearchText=DHT22+AM2302+temperature+humidity+sensor", 18, 5, True, "Clone modules, verify calibration", 6.0),
        SupplierOption("Chengdu - Seg Electronics", "Chengdu, China", 4.50, "USD", "", 1, 1, True, "Seg Plaza, Tianfu Square area. Test before buying.", 7.5),
        SupplierOption("Taobao - LCSC Mall", "Online - China", 2.80, "USD", "https://www.lcsc.com/search?q=DHT22", 3, 5, True, "Aosong genuine parts via LCSC", 8.0),
    ]
)

# ── WATER QUALITY SENSORS ──
ITEM_PH_PROBE = SourcedBOMItem(
    part_number="Atlas Scientific EZO-pH",
    description="Industrial pH Sensor Kit with EZO carrier board, I2C/UART",
    category="sensor",
    qty=2,
    datasheet_url="https://atlas-scientific.com/ezo-ph-circuit/",
    notes="Tilapia need pH 6.5–8.5. Calibrate monthly with 4.0 / 7.0 / 10.0 buffers.",
    options=[
        SupplierOption("Atlas Scientific Direct", "Online - USA", 199.00, "USD", "https://atlas-scientific.com/ezo-ph-circuit/", 14, 1, True, "Garanteed genuine, calibration solutions included", 10.0),
        SupplierOption("Amazon - Atlas Scientific Store", "Online - Global", 215.00, "USD", "https://www.amazon.com/s?k=Atlas+Scientific+EZO+pH", 7, 1, True, "Prime shipping, slightly more expensive", 9.5),
        SupplierOption("AliExpress - Industrial Sensor Co", "Online - China", 145.00, "USD", "https://www.aliexpress.com/wholesale?SearchText=Atlas+Scientific+EZO+pH", 21, 1, True, "Verify clone vs genuine before purchase", 5.0),
        SupplierOption("Taobao - Defeilai Flagship Store", "Online - China", 85.00, "USD", "", 5, 1, True, "EZO clone board + BNC probe bundle. Calibrate before use.", 6.0),
        SupplierOption("1688.com - Shenzhen Sensor Wholesale", "Online - China", 55.00, "USD", "", 5, 5, True, "Wholesale pH probe + signal conditioner. Bulk pricing.", 5.5),
        SupplierOption("Pinduoduo - Aquarium Sensor Shop", "Online - China", 35.00, "USD", "", 5, 1, True, "Generic BNC pH probe + PH-4502C module. Read reviews. Very cheap.", 4.0),
    ]
)

ITEM_DO_PROBE = SourcedBOMItem(
    part_number="Atlas Scientific EZO-DO",
    description="Dissolved Oxygen Sensor Kit",
    category="sensor",
    qty=2,
    datasheet_url="https://atlas-scientific.com/ezo-dissolved-oxygen-circuit/",
    notes="Minimum 4 mg/L for tilapia. Below 3 mg/L triggers emergency aeration.",
    options=[
        SupplierOption("Atlas Scientific Direct", "Online - USA", 359.00, "USD", "https://atlas-scientific.com/ezo-dissolved-oxygen-circuit/", 14, 1, True, "Genuine, includes calibration cap", 10.0),
        SupplierOption("Amazon - Atlas Scientific Store", "Online - Global", 385.00, "USD", "https://www.amazon.com/s?k=Atlas+Scientific+EZO+dissolved+oxygen", 7, 1, True, "Prime shipping", 9.5),
        SupplierOption("AliExpress - Sensor World", "Online - China", 260.00, "USD", "https://www.aliexpress.com/wholesale?SearchText=dissolved+oxygen+sensor+aquarium", 21, 1, True, "Check reviews carefully", 5.5),
        SupplierOption("Taobao - Greenlink Sensor Store", "Online - China", 120.00, "USD", "", 5, 1, True, "Optical DO sensor clone. Works for monitoring. Verify accuracy.", 5.5),
        SupplierOption("1688.com - Shanghai Water Quality Instruments", "Online - China", 85.00, "USD", "", 5, 2, True, "Chinese optical DO probe wholesale. Ask for calibration cert.", 5.0),
        SupplierOption("Pinduoduo - Aquaculture Equipment Store", "Online - China", 45.00, "USD", "", 5, 1, True, "Pen-style DO meter, not continuous. Use for spot-checking only.", 3.5),
    ]
)

# ── FLOW SENSORS ──
ITEM_FLOW = SourcedBOMItem(
    part_number="YF-S201",
    description="Hall-effect Water Flow Sensor, 1-30 L/min, 1/2\" NPT",
    category="sensor",
    qty=4,
    datasheet_url="https://www.seeedstudio.com/Water-Flow-Sensor-YF-S201-p-1345.html",
    notes="Pulse output: 450 pulses/L. Mount on pump discharge. Interrupt-driven on ESP32.",
    options=[
        SupplierOption("Amazon - Seeed Studio", "Online - Global", 8.50, "USD", "https://www.amazon.com/s?k=YF-S201+water+flow+sensor", 7, 1, True, "Genuine Seeed, consistent quality", 9.0),
        SupplierOption("Taobao - Flow Sensor Wholesale", "Online - China", 2.00, "USD", "", 5, 1, True, "Standard hall-effect flow sensor. NPT 1/2\".", 7.0),
        SupplierOption("1688.com - Flow Meter Factory", "Online - China", 1.40, "USD", "", 5, 10, True, "Factory direct. Plastic body. Test pulse count.", 6.0),
        SupplierOption("Pinduoduo - Sensor Parts Store", "Online - China", 1.00, "USD", "", 5, 1, True, "Cheapest. Check Hall element sensitivity.", 4.5),
        SupplierOption("JD.com - JD Electronics", "Online - China", 2.80, "USD", "", 2, 1, True, "JD official store. Reliable quality. Fast ship.", 8.0),
        SupplierOption("AliExpress - Sensor Depot", "Online - China", 2.80, "USD", "https://www.aliexpress.com/wholesale?SearchText=YF-S201+water+flow+sensor", 18, 5, True, "Very cheap, test flow accuracy", 6.5),
        SupplierOption("Chengdu - Chuanke Electronics", "Chengdu, China", 4.00, "USD", "", 1, 1, True, "Local stock", 7.5),
        SupplierOption("Taobao - LCSC Mall", "Online - China", 2.50, "USD", "https://www.lcsc.com/search?q=YF-S201", 3, 5, True, "Bulk friendly", 8.0),
    ]
)

# ── RELAY BOARDS ──
ITEM_RELAY_8CH = SourcedBOMItem(
    part_number="HW-483 / 8-Channel Relay",
    description="5V logic, 8x SONGLE relays, 10A each, optocoupler isolation",
    category="actuator",
    qty=3,
    datasheet_url="https://wiki.keyestudio.com/KS0260_Keyestudio_8_Channel_5V_Relay_Module",
    notes="Low-level trigger (LOW = relay energizes). VCC→5V, IN→ESP32 GPIOs via 1kΩ.",
    options=[
        SupplierOption("Amazon - Keyestudio", "Online - Global", 12.00, "USD", "https://www.amazon.com/s?k=8+channel+relay+module+5V+SONGLE", 7, 1, True, "Well-documented, reliable", 9.0),
        SupplierOption("Taobao - Relay Module Wholesale", "Online - China", 3.50, "USD", "", 5, 1, True, "SONGLE relay modules. Check optocoupler is populated.", 7.0),
        SupplierOption("1688.com - Relay Factory", "Online - China", 2.20, "USD", "", 5, 10, True, "Factory direct relay boards. Bulk pricing.", 6.5),
        SupplierOption("Pinduoduo - Electronics Parts Store", "Online - China", 1.80, "USD", "", 5, 1, True, "Very cheap. Verify relay rating and optocoupler.", 5.0),
        SupplierOption("JD.com - JD Electronics", "Online - China", 4.00, "USD", "", 2, 1, True, "JD official store. Reliable modules.", 8.0),
        SupplierOption("AliExpress - Relay World", "Online - China", 4.50, "USD", "https://www.aliexpress.com/wholesale?SearchText=8+channel+relay+module+5V", 18, 2, True, "Cheap but check relay contact rating", 6.0),
        SupplierOption("Chengdu - Seg Electronics", "Chengdu, China", 6.00, "USD", "", 1, 1, True, "Test with multimeter before leaving store", 7.0),
        SupplierOption("Taobao - LCSC Mall", "Online - China", 3.80, "USD", "https://www.lcsc.com/search?q=relay+module", 3, 5, True, "Good for volume", 7.5),
    ]
)

# ── PUMPS ──
ITEM_PUMP_CIRC = SourcedBOMItem(
    part_number="EcoPlus 728310 / 396 GPH",
    description="Submersible Circulation Pump, 396 GPH, 15W, 120V",
    category="pump",
    qty=2,
    datasheet_url="https://www.hydrofarm.com",
    notes="Primary loop: tank → biofilter → grow bed → sump → HX → tank. One primary + backup.",
    options=[
        SupplierOption("Amazon - Hydrofarm", "Online - Global", 24.99, "USD", "https://www.amazon.com/s?k=EcoPlus+submersible+water+pump+396+GPH", 5, 1, True, "Fast shipping, good warranty", 9.0),
        SupplierOption("Hydrofarm Direct", "Online - USA", 22.50, "USD", "https://www.hydrofarm.com", 10, 1, True, "Slightly cheaper direct, longer ship", 9.0),
        SupplierOption("Taobao - Sunsun Aquarium Official", "Online - China", 16.00, "USD", "", 5, 1, True, "Sunsun brand. Popular in China. 25W submersible.", 7.5),
        SupplierOption("1688.com - Aquarium Pump Factory", "Online - China", 11.00, "USD", "", 5, 5, True, "Factory direct. Test flow rate on arrival.", 6.5),
        SupplierOption("Pinduoduo - Aquarium Supplies", "Online - China", 8.50, "USD", "", 5, 1, True, "Very cheap. Check motor noise and flow.", 5.0),
        SupplierOption("JD.com - JD Aquarium", "Online - China", 18.00, "USD", "", 2, 1, True, "JD official store. Next-day delivery in major cities.", 8.0),
        SupplierOption("AliExpress - Pump Depot", "Online - China", 14.00, "USD", "https://www.aliexpress.com/wholesale?SearchText=submersible+water+pump+396+GPH+aquarium", 21, 1, True, "Chinese clone, check flow rating", 5.5),
        SupplierOption("Chengdu - Jingu Aquarium", "Chengdu, China", 18.00, "USD", "", 1, 1, True, "Local aquarium supplier. Test flow in-store.", 7.5),
    ]
)

ITEM_PUMP_AIR = SourcedBOMItem(
    part_number="Hydrofarm AAPA45L / 20W",
    description="Linear Air Pump, 25 L/min, 20W, 120V",
    category="pump",
    qty=2,
    datasheet_url="https://www.hydrofarm.com/p/active-aqua-air-pump/",
    notes="Aeration for tanks. Run continuously. Second pump on standby relay.",
    options=[
        SupplierOption("Amazon - Hydrofarm", "Online - Global", 39.99, "USD", "https://www.amazon.com/s?k=aquarium+air+pump+25L+linear", 5, 1, True, "Fast, reliable", 9.0),
        SupplierOption("Taobao - Sunsun Air Pump", "Online - China", 18.00, "USD", "", 5, 1, True, "Sunsun air pump. 25L/min. Quiet operation.", 7.5),
        SupplierOption("1688.com - Air Pump Wholesale", "Online - China", 12.00, "USD", "", 5, 5, True, "Wholesale. Test noise level.", 6.5),
        SupplierOption("Pinduoduo - Aquaculture Equipment", "Online - China", 9.00, "USD", "", 5, 1, True, "Budget air pump. May be loud. Fine for backup.", 5.0),
        SupplierOption("JD.com - JD Aquarium Equipment", "Online - China", 20.00, "USD", "", 2, 1, True, "JD official store. Reliable. Fast ship.", 8.0),
        SupplierOption("AliExpress - Aquatic World", "Online - China", 22.00, "USD", "https://www.aliexpress.com/wholesale?SearchText=aquarium+air+pump+25L+min", 21, 1, True, "Check noise level reviews", 6.0),
        SupplierOption("Chengdu - Jingu Aquarium", "Chengdu, China", 28.00, "USD", "", 1, 1, True, "Local aquarium shop", 7.5),
    ]
)

# ── HEAT EXCHANGER ──
ITEM_HEX = SourcedBOMItem(
    part_number="Brazed Plate HX, 30-plate, 3x8\"",
    description="Stainless steel 316L, 30 plates, 3\"x8\" ports, 60k BTU/hr",
    category="heat_exchanger",
    qty=1,
    datasheet_url="https://www.dudadiesel.com/brazed-plate-heat-exchanger-stainless-steel-316l-30-plate/",
    notes="Server liquid cooling (hot) → aquaculture water (cold). Counter-flow for max efficiency.",
    options=[
        SupplierOption("Amazon - Duda Diesel", "Online - Global", 189.00, "USD", "https://www.amazon.com/s?k=brazed+plate+heat+exchanger+30+plate+316L", 7, 1, True, "Prime shipping, good reviews", 9.0),
        SupplierOption("Duda Diesel Direct", "Online - USA", 175.00, "USD", "https://dudadiesel.com", 10, 1, True, "Cheaper direct, ships from Michigan", 9.0),
        SupplierOption("AliExpress - HVAC Components", "Online - China", 95.00, "USD", "https://www.aliexpress.com/wholesale?SearchText=brazed+plate+heat+exchanger+stainless+steel", 28, 1, True, "Much cheaper but verify 316L grade", 5.0),
        SupplierOption("Taobao - Heat Exchanger Factory Direct", "Online - China", 68.00, "USD", "", 5, 1, True, "Domestic Chinese brazed HX. Ask for pressure test report.", 6.0),
        SupplierOption("1688.com - Zhejiang Plate HX Factory", "Online - China", 55.00, "USD", "", 5, 1, True, "Factory direct. 304 stainless standard. Specify 316L if needed.", 5.5),
        SupplierOption("Chengdu - Sichuan HVAC Supply", "Chengdu, China", 140.00, "USD", "", 3, 1, True, "Industrial HVAC supplier. Can verify material cert.", 8.0),
    ]
)

# ── CONTROLLERS ──
ITEM_ESP32 = SourcedBOMItem(
    part_number="ESP32-DevKitC-32E",
    description="ESP32-WROOM-32E DevKit, WiFi + Bluetooth, 38 pins",
    category="controller",
    qty=4,
    datasheet_url="https://docs.espressif.com/projects/esp-idf/en/latest/esp32/hw-reference/esp32/get-started-devkitc.html",
    notes="One per subsystem: (1) Tank telemetry, (2) Grow bed telemetry, (3) Server thermal + relay, (4) Filtration + flow.",
    options=[
        SupplierOption("Amazon - Espressif Official", "Online - Global", 8.99, "USD", "https://www.amazon.com/s?k=ESP32+DevKitC+WROOM-32E", 5, 1, True, "Genuine Espressif, best reliability", 9.5),
        SupplierOption("Taobao - Espressif Official Store", "Online - China", 4.50, "USD", "", 5, 1, True, "Espressif official Taobao store. Genuine boards.", 9.0),
        SupplierOption("1688.com - Shenzhen Electronics Wholesale", "Online - China", 2.80, "USD", "", 5, 10, True, "AI-Thinker modules wholesale. Check solder quality.", 7.0),
        SupplierOption("Pinduoduo - Electronic Components", "Online - China", 2.20, "USD", "", 5, 1, True, "Cheapest ESP32. May be old revision. Test WiFi range.", 5.0),
        SupplierOption("JD.com - JD Electronic Components", "Online - China", 5.00, "USD", "", 2, 1, True, "JD official store electronics. Genuine, fast shipping.", 8.5),
        SupplierOption("AliExpress - AI-Thinker Store", "Online - China", 3.50, "USD", "https://www.aliexpress.com/wholesale?SearchText=ESP32+DevKitC+WROOM-32E", 15, 2, True, "AI-Thinker modules, generally good", 7.5),
        SupplierOption("Chengdu - Chuanke Electronics", "Chengdu, China", 5.00, "USD", "", 1, 1, True, "Local, can inspect PCB quality", 8.0),
        SupplierOption("Taobao - LCSC Mall", "Online - China", 3.20, "USD", "https://www.lcsc.com/search?q=ESP32-DevKitC", 3, 5, True, "LCSC genuine, great for volume", 8.5),
    ]
)

ITEM_RPI5 = SourcedBOMItem(
    part_number="Raspberry Pi 5 / 8GB",
    description="Main compute node for SimplePod Swarm backend",
    category="controller",
    qty=1,
    datasheet_url="https://www.raspberrypi.com/products/raspberry-pi-5/",
    notes="Runs FastAPI backend. Mount in NEMA enclosure. PoE+ HAT recommended.",
    options=[
        SupplierOption("Amazon - CanaKit", "Online - Global", 80.00, "USD", "https://www.amazon.com/s?k=Raspberry+Pi+5+8GB", 5, 1, True, "Bundle with case + PSU available", 9.5),
        SupplierOption("PiShop.us", "Online - USA", 75.00, "USD", "https://pishop.us", 7, 1, True, "Often better stock than Amazon", 9.0),
        SupplierOption("Taobao - Raspberry Pi Official", "Online - China", 72.00, "USD", "", 5, 1, True, "Official reseller on Taobao. Domestic warranty.", 8.5),
        SupplierOption("JD.com - JD Self-operated", "Online - China", 75.00, "USD", "", 3, 1, True, "JD official store fast shipping, genuine guaranteed.", 9.0),
        SupplierOption("Pinduoduo - Digital Subsidies", "Online - China", 65.00, "USD", "", 5, 1, True, "Subsidy price. Verify seller rating before purchase.", 7.0),
        SupplierOption("Chengdu - Chuanke Electronics", "Chengdu, China", 78.00, "USD", "", 1, 1, True, "Local gray-market import. Check warranty.", 7.0),
    ]
)

# ── ENCLOSURES ──
ITEM_ENCLOSURE = SourcedBOMItem(
    part_number="BUD Industries NBF-32016",
    description="NEMA 4X Polycarbonate Enclosure, 12x10x6\", hinged lid",
    category="enclosure",
    qty=4,
    datasheet_url="https://www.budind.com/product/nema-4x-polycarbonate-enclosures/",
    notes="One per ESP32. Vented with insect screen + desiccant. Cable glands for sensor wires.",
    options=[
        SupplierOption("Digi-Key", "Online - Global", 45.00, "USD", "https://www.digikey.com/en/products/result?keywords=NBF-32016", 5, 1, True, "Genuine BUD, fast shipping", 10.0),
        SupplierOption("Mouser", "Online - Global", 43.50, "USD", "https://www.mouser.com/Search/Refine?Keyword=NBF-32016", 5, 1, True, "Competitive pricing", 10.0),
        SupplierOption("Amazon - BUD Industries", "Online - Global", 52.00, "USD", "https://www.amazon.com/s?k=BUD+Industries+NBF-32016+NEMA+4X", 5, 1, True, "Prime convenience", 9.0),
        SupplierOption("Taobao - Waterproof Box Wholesale", "Online - China", 12.00, "USD", "", 5, 1, True, "ABS plastic IP65 box. Drill ventilation holes yourself.", 6.5),
        SupplierOption("1688.com - Yueqing Electrical Box Factory", "Online - China", 8.50, "USD", "", 5, 10, True, "Yueqing factory direct. ABS + PC blend. Very cheap.", 5.5),
        SupplierOption("Pinduoduo - Electrical Shop", "Online - China", 6.00, "USD", "", 5, 1, True, "Basic IP65 box. Check wall thickness in reviews.", 4.5),
        SupplierOption("AliExpress - Enclosure World", "Online - China", 18.00, "USD", "https://www.aliexpress.com/wholesale?SearchText=NEMA+4X+enclosure+waterproof+electronic", 21, 1, True, "Verify IP rating before buying", 5.0),
        SupplierOption("Chengdu - Seg Electronics", "Chengdu, China", 22.00, "USD", "", 1, 1, True, "Local IP65 boxes. May need to add gasket.", 6.5),
    ]
)

# ── POWER ──
ITEM_PSU = SourcedBOMItem(
    part_number="MEAN WELL LRS-50-5",
    description="5V DC Switching PSU, 10A, 50W, DIN rail mount",
    category="power",
    qty=2,
    datasheet_url="https://www.meanwell.com/Upload/PDF/LRS-50/LRS-50-SPEC.PDF",
    notes="Powers ESP32s, relay boards, sensors. One per control panel. Fused at breaker.",
    options=[
        SupplierOption("Digi-Key", "Online - Global", 18.50, "USD", "https://www.digikey.com/en/products/result?keywords=LRS-50-5", 5, 1, True, "Genuine MEAN WELL, fast", 10.0),
        SupplierOption("Mouser", "Online - Global", 17.80, "USD", "https://www.mouser.com/Search/Refine?Keyword=LRS-50-5", 5, 1, True, "Slightly cheaper", 10.0),
        SupplierOption("Amazon - MEAN WELL", "Online - Global", 22.00, "USD", "https://www.amazon.com/s?k=MEAN+WELL+LRS-50-5", 5, 1, True, "Prime", 9.0),
        SupplierOption("Taobao - MEAN WELL Official", "Online - China", 14.00, "USD", "", 5, 1, True, "Genuine MEAN WELL China distributor. Better price than Amazon.", 8.5),
        SupplierOption("1688.com - MEAN WELL Wholesale", "Online - China", 10.50, "USD", "", 5, 5, True, "Wholesale MEAN WELL. Verify serial number online.", 8.0),
        SupplierOption("Pinduoduo - Power Module Shop", "Online - China", 5.50, "USD", "", 5, 1, True, "Generic 5V10A switching PSU. Not MEAN WELL. Test ripple.", 4.5),
        SupplierOption("AliExpress - Power Supply Depot", "Online - China", 8.50, "USD", "https://www.aliexpress.com/wholesale?SearchText=MEAN+WELL+LRS-50-5", 18, 5, True, "Clone risk — check efficiency ripple", 5.0),
        SupplierOption("Chengdu - Chuanke Electronics", "Chengdu, China", 12.00, "USD", "", 1, 1, True, "Local. Test load regulation.", 7.0),
    ]
)

# ── MISCELLANEOUS (wire, conduit, etc.) ──
ITEM_WIRE_22AWG = SourcedBOMItem(
    part_number="22 AWG Stranded Wire, UL1007",
    description="Hook-up wire, 22 AWG, stranded, 300V, assorted colors",
    category="misc",
    qty=5,  # 5 spools of 100ft each
    datasheet_url="",
    notes="Sensor wiring. Use red for VCC, black for GND, colored for signals.",
    options=[
        SupplierOption("Amazon - Tuofeng", "Online - Global", 12.99, "USD", "https://www.amazon.com/s?k=22+AWG+stranded+wire+UL1007+assorted", 5, 1, True, "6-color kit, 25ft each", 8.5),
        SupplierOption("Taobao - Wire & Cable Wholesale", "Online - China", 2.20, "USD", "", 5, 1, True, "100m reel 22AWG UL1007. Multiple colors.", 7.5),
        SupplierOption("1688.com - Cable Factory", "Online - China", 1.50, "USD", "", 5, 10, True, "Factory direct wire. 100m reels. Very cheap.", 6.5),
        SupplierOption("Pinduoduo - Hardware Electrical", "Online - China", 1.00, "USD", "", 5, 1, True, "Budget wire. Check copper purity (should be tinned).", 5.0),
        SupplierOption("Chengdu - Seg Electronics", "Chengdu, China", 3.50, "USD", "", 1, 1, True, "By-the-meter pricing. Bring wire gauge tool.", 7.0),
        SupplierOption("Taobao - LCSC Mall", "Online - China", 2.80, "USD", "https://www.lcsc.com/search?q=UL1007+22AWG", 3, 10, True, "Bulk reels, good quality", 8.0),
    ]
)

ITEM_CONDUIT = SourcedBOMItem(
    part_number="Liquid-Tight Flexible Conduit, 1/2\", 100ft",
    description="Non-metallic liquid-tight flexible conduit, 1/2\" diameter",
    category="misc",
    qty=1,
    datasheet_url="",
    notes="Protect sensor wires from moisture. Run from NEMA boxes to tank areas.",
    options=[
        SupplierOption("Amazon - Sealproof", "Online - Global", 45.00, "USD", "https://www.amazon.com/s?k=liquid+tight+flexible+conduit+1%2F2+inch+100ft", 5, 1, True, "100ft roll, fittings included", 8.5),
        SupplierOption("Home Depot / Lowe's", "Local - USA", 38.00, "USD", "", 1, 1, True, "In-store pickup", 9.0),
        SupplierOption("Taobao - Conduit Wholesale", "Online - China", 12.00, "USD", "", 5, 1, True, "16mm flexible plastic conduit. 30m roll.", 6.5),
        SupplierOption("1688.com - Conduit Factory", "Online - China", 8.00, "USD", "", 5, 5, True, "Factory direct. PVC flexible conduit. Bulk pricing.", 6.0),
        SupplierOption("Pinduoduo - Hardware Building Materials", "Online - China", 6.50, "USD", "", 5, 1, True, "Budget conduit. Check wall thickness.", 4.5),
        SupplierOption("Chengdu - Hardware Market", "Chengdu, China", 15.00, "USD", "", 1, 1, True, "Local hardware market. Verify UV rating.", 6.5),
    ]
)

ITEM_WAGO = SourcedBOMItem(
    part_number="Wago 221-412 Lever Nuts",
    description="2-conductor lever splice connector, 0.14-4mm², 32A",
    category="misc",
    qty=50,
    datasheet_url="https://www.wago.com/global/compact-splicing-connector/221-412/",
    notes="Use for ALL connections near moisture. Never use wire nuts in wet locations.",
    options=[
        SupplierOption("Amazon - Wago Official", "Online - Global", 0.45, "USD", "https://www.amazon.com/s?k=Wago+221-412+lever+nuts", 5, 50, True, "50-pack box, genuine Wago", 9.5),
        SupplierOption("Digi-Key", "Online - Global", 0.38, "USD", "https://www.digikey.com/en/products/result?keywords=221-412", 5, 100, True, "Best price at volume", 10.0),
        SupplierOption("Taobao - WAGO Official", "Online - China", 0.28, "USD", "", 5, 50, True, "Genuine Wago China distributor. Bulk box.", 8.5),
        SupplierOption("1688.com - Terminal Block Wholesale", "Online - China", 0.15, "USD", "", 5, 100, True, "Wago-style lever nuts. Good clones. Check spring tension.", 6.0),
        SupplierOption("Pinduoduo - Electrical Parts", "Online - China", 0.08, "USD", "", 5, 50, True, "Very cheap clones. Test pull-out force before using.", 4.0),
        SupplierOption("Chengdu - Seg Electronics", "Chengdu, China", 0.30, "USD", "", 1, 50, True, "Local. Check for knockoffs — genuine Wago has laser marking.", 6.5),
    ]
)

# ── BACKUP HEATER (important for thermal balance) ──
ITEM_HEATER = SourcedBOMItem(
    part_number="EcoPlus 728340 / 300W Submersible Heater",
    description="300W titanium submersible aquarium heater, 0-40°C thermostat",
    category="actuator",
    qty=2,
    datasheet_url="https://www.hydrofarm.com/p/ecoplus-titanium-heater/",
    notes="Backup heat for cold nights. Thermal analysis shows -37W net loss. These provide margin.",
    options=[
        SupplierOption("Amazon - Hydrofarm", "Online - Global", 34.99, "USD", "https://www.amazon.com/s?k=EcoPlus+titanium+aquarium+heater+300W", 5, 1, True, "Titanium, corrosion-proof", 9.0),
        SupplierOption("Taobao - Sunsun Heater", "Online - China", 12.00, "USD", "", 5, 1, True, "Sunsun 300W quartz heater. Common brand in China.", 7.0),
        SupplierOption("1688.com - Aquarium Heater Wholesale", "Online - China", 8.50, "USD", "", 5, 5, True, "Wholesale quartz heaters. Verify thermostat accuracy.", 6.0),
        SupplierOption("Pinduoduo - Aquarium Supplies", "Online - China", 6.00, "USD", "", 5, 1, True, "Budget heater. Must have auto-shutoff. Read reviews.", 4.5),
        SupplierOption("JD.com - JD Aquarium", "Online - China", 14.00, "USD", "", 2, 1, True, "JD official store. Reliable brands. Fast shipping.", 8.0),
        SupplierOption("Chengdu - Jingu Aquarium", "Chengdu, China", 22.00, "USD", "", 1, 1, True, "Local aquarium supplier", 7.5),
        SupplierOption("AliExpress - Aquarium World", "Online - China", 15.00, "USD", "https://www.aliexpress.com/wholesale?SearchText=titanium+aquarium+heater+300W", 18, 1, True, "Check thermostat accuracy", 5.5),
    ]
)


ALL_ITEMS: List[SourcedBOMItem] = [
    ITEM_DS18B20, ITEM_DHT22, ITEM_PH_PROBE, ITEM_DO_PROBE, ITEM_FLOW,
    ITEM_RELAY_8CH, ITEM_PUMP_CIRC, ITEM_PUMP_AIR, ITEM_HEX,
    ITEM_ESP32, ITEM_RPI5, ITEM_ENCLOSURE, ITEM_PSU,
    ITEM_WIRE_22AWG, ITEM_CONDUIT, ITEM_WAGO, ITEM_HEATER,
]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION C: BUILD PROFILES — PRE-CONFIGURED SOURCING STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BuildProfile:
    """A pre-configured sourcing strategy for the entire BOM."""
    name: str
    description: str
    icon: str
    strategy: str                    # "price", "speed", "reliability", "local", "custom"
    item_selections: Dict[str, int]  # part_number -> option index
    color: str = "blue"

    def compute_total(self) -> dict:
        """Calculate total cost and sourcing breakdown."""
        total = 0.0
        by_supplier = {}
        by_location = {}
        max_shipping = 0
        items = []
        for item in ALL_ITEMS:
            idx = self.item_selections.get(item.part_number, 0)
            opt = item.options[idx] if idx < len(item.options) else item.options[0]
            ext = opt.unit_price_usd * item.qty
            total += ext
            by_supplier[opt.supplier_name] = by_supplier.get(opt.supplier_name, 0) + ext
            by_location[opt.location] = by_location.get(opt.location, 0) + ext
            max_shipping = max(max_shipping, opt.shipping_days)
            items.append({
                "part_number": item.part_number,
                "description": item.description,
                "qty": item.qty,
                "supplier": opt.supplier_name,
                "location": opt.location,
                "unit_price": opt.unit_price_usd,
                "extended": ext,
                "shipping_days": opt.shipping_days,
            })
        return {
            "profile_name": self.name,
            "total_usd": round(total, 2),
            "max_shipping_days": max_shipping,
            "by_supplier": by_supplier,
            "by_location": by_location,
            "item_count": len(items),
            "suppliers_needed": len(by_supplier),
            "items": items,
        }


# Budget: cheapest option for every item
BUDGET_BUILD = BuildProfile(
    name="Budget Build",
    description="Cheapest sourcing option for every part. Expect longer shipping times and some clone-quality components. Good for proof-of-concept.",
    icon="💰",
    strategy="price",
    color="yellow",
    item_selections={
        "DS18B20": 3,           # Taobao LCSC @ $1.50
        "DHT22 / AM2302": 3,    # Taobao LCSC @ $2.80
        "Atlas Scientific EZO-pH": 2,  # AliExpress @ $145
        "Atlas Scientific EZO-DO": 2,  # AliExpress @ $260
        "YF-S201": 3,           # Taobao LCSC @ $2.50
        "HW-483 / 8-Channel Relay": 3, # Taobao LCSC @ $3.80
        "EcoPlus 728310 / 396 GPH": 2, # AliExpress @ $14
        "Hydrofarm AAPA45L / 20W": 1,  # Amazon @ $39.99 (no cheap clone)
        "Brazed Plate HX, 30-plate, 3x8\"": 2,  # AliExpress @ $95
        "ESP32-DevKitC-32E": 2,        # AliExpress @ $3.50
        "Raspberry Pi 5 / 8GB": 1,     # Amazon @ $80
        "BUD Industries NBF-32016": 3, # AliExpress @ $18
        "MEAN WELL LRS-50-5": 3,       # AliExpress @ $8.50
        "22 AWG Stranded Wire, UL1007": 2, # Chengdu @ $3.50/spool
        "Liquid-Tight Flexible Conduit, 1/2\", 100ft": 2, # Chengdu @ $15
        "Wago 221-412 Lever Nuts": 2,  # Chengdu @ $0.30
        "EcoPlus 728340 / 300W Submersible Heater": 2, # AliExpress @ $15
    }
)

# Standard: balanced price/quality
STANDARD_BUILD = BuildProfile(
    name="Standard Build",
    description="Balanced sourcing — genuine parts where it matters (sensors, controllers), savings on commodities (wire, enclosures). Recommended for production.",
    icon="⚖️",
    strategy="reliability",
    color="blue",
    item_selections={
        "DS18B20": 0,           # Amazon @ $4.50
        "DHT22 / AM2302": 0,    # Amazon Adafruit @ $9.95
        "Atlas Scientific EZO-pH": 0,  # Atlas Direct @ $199
        "Atlas Scientific EZO-DO": 0,  # Atlas Direct @ $359
        "YF-S201": 0,           # Amazon Seeed @ $8.50
        "HW-483 / 8-Channel Relay": 0, # Amazon Keyestudio @ $12
        "EcoPlus 728310 / 396 GPH": 0, # Amazon Hydrofarm @ $24.99
        "Hydrofarm AAPA45L / 20W": 0,  # Amazon @ $39.99
        "Brazed Plate HX, 30-plate, 3x8\"": 0,  # Amazon Duda @ $189
        "ESP32-DevKitC-32E": 0,        # Amazon Espressif @ $8.99
        "Raspberry Pi 5 / 8GB": 1,     # PiShop @ $75
        "BUD Industries NBF-32016": 0, # Amazon BUD @ $52
        "MEAN WELL LRS-50-5": 0,       # Amazon @ $22
        "22 AWG Stranded Wire, UL1007": 0, # Amazon @ $12.99
        "Liquid-Tight Flexible Conduit, 1/2\", 100ft": 0, # Amazon @ $45
        "Wago 221-412 Lever Nuts": 0,  # Amazon @ $0.45
        "EcoPlus 728340 / 300W Submersible Heater": 0, # Amazon @ $34.99
    }
)

# Premium: fastest + most reliable
PREMIUM_BUILD = BuildProfile(
    name="Premium Build",
    description="Fastest shipping, genuine parts everywhere, local Chengdu sourcing where possible. For time-critical deployments.",
    icon="🚀",
    strategy="speed",
    color="emerald",
    item_selections={
        "DS18B20": 2,           # Chengdu local @ $2.20
        "DHT22 / AM2302": 2,    # Chengdu Seg @ $4.50
        "Atlas Scientific EZO-pH": 1,  # Amazon @ $215 (faster than Atlas direct)
        "Atlas Scientific EZO-DO": 1,  # Amazon @ $385
        "YF-S201": 2,           # Chengdu @ $4.00
        "HW-483 / 8-Channel Relay": 2, # Chengdu @ $6.00
        "EcoPlus 728310 / 396 GPH": 3, # Chengdu aquarium @ $18
        "Hydrofarm AAPA45L / 20W": 2,  # Chengdu @ $28
        "Brazed Plate HX, 30-plate, 3x8\"": 3,  # Chengdu HVAC @ $140
        "ESP32-DevKitC-32E": 2,        # Chengdu @ $5.00
        "Raspberry Pi 5 / 8GB": 2,     # Chengdu @ $78
        "BUD Industries NBF-32016": 2, # Chengdu Seg @ $22
        "MEAN WELL LRS-50-5": 2,       # Chengdu @ $12
        "22 AWG Stranded Wire, UL1007": 2, # Chengdu @ $3.50
        "Liquid-Tight Flexible Conduit, 1/2\", 100ft": 2, # Chengdu @ $15
        "Wago 221-412 Lever Nuts": 2,  # Chengdu @ $0.30
        "EcoPlus 728340 / 300W Submersible Heater": 1, # Chengdu @ $22
    }
)

# Local Chengdu: everything from local suppliers
CHENGDU_BUILD = BuildProfile(
    name="Chengdu Local",
    description="Source everything from Chengdu local markets — Chuanke Electronics, Seg Plaza, Jingu Aquarium. Same-day pickup for most items.",
    icon="🏪",
    strategy="local",
    color="orange",
    item_selections={
        "DS18B20": 2,
        "DHT22 / AM2302": 2,
        "Atlas Scientific EZO-pH": 1,  # No local source — fall back to Amazon
        "Atlas Scientific EZO-DO": 1,  # No local source — fall back to Amazon
        "YF-S201": 2,
        "HW-483 / 8-Channel Relay": 2,
        "EcoPlus 728310 / 396 GPH": 3,
        "Hydrofarm AAPA45L / 20W": 2,
        "Brazed Plate HX, 30-plate, 3x8\"": 3,
        "ESP32-DevKitC-32E": 2,
        "Raspberry Pi 5 / 8GB": 2,
        "BUD Industries NBF-32016": 2,
        "MEAN WELL LRS-50-5": 2,
        "22 AWG Stranded Wire, UL1007": 2,
        "Liquid-Tight Flexible Conduit, 1/2\", 100ft": 2,
        "Wago 221-412 Lever Nuts": 2,
        "EcoPlus 728340 / 300W Submersible Heater": 1,
    }
)

# Dabao Special: absolute cheapest from Chinese domestic marketplaces
DABAO_BUILD = BuildProfile(
    name="Dabao Special",
    description="Ultra budget plan — source everything from Taobao, 1688, Pinduoduo. For tight budgets, accepting domestic alternatives. Total can be kept under $1000.",
    icon="🧧",
    strategy="price",
    color="purple",
    item_selections={
        "DS18B20": 6,           # Pinduoduo @ $0.70
        "DHT22 / AM2302": 4,    # Pinduoduo @ $1.20
        "Atlas Scientific EZO-pH": 5,  # Pinduoduo generic pH @ $35
        "Atlas Scientific EZO-DO": 5,  # Pinduoduo pen-style DO @ $45 (spot check only)
        "YF-S201": 4,           # Pinduoduo @ $1.00
        "HW-483 / 8-Channel Relay": 4, # Pinduoduo @ $1.80
        "EcoPlus 728310 / 396 GPH": 5, # Pinduoduo @ $8.50
        "Hydrofarm AAPA45L / 20W": 4,  # Pinduoduo @ $9.00
        "Brazed Plate HX, 30-plate, 3x8\"": 4,  # 1688 @ $55
        "ESP32-DevKitC-32E": 4,        # Pinduoduo @ $2.20
        "Raspberry Pi 5 / 8GB": 4,     # Pinduoduo @ $65
        "BUD Industries NBF-32016": 5, # Pinduoduo @ $6.00
        "MEAN WELL LRS-50-5": 5,       # Pinduoduo generic @ $5.50
        "22 AWG Stranded Wire, UL1007": 4, # Pinduoduo @ $1.00/spool
        "Liquid-Tight Flexible Conduit, 1/2\", 100ft": 4, # Pinduoduo @ $6.50
        "Wago 221-412 Lever Nuts": 5,  # Pinduoduo @ $0.08
        "EcoPlus 728340 / 300W Submersible Heater": 4, # Pinduoduo @ $6.00
    }
)

ALL_PROFILES = [DABAO_BUILD, BUDGET_BUILD, STANDARD_BUILD, PREMIUM_BUILD, CHENGDU_BUILD]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION D: BUILD ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BuildAnalysisReport:
    """Comprehensive engineering and sourcing report for a build configuration."""
    profile_name: str
    generated_at: str

    # Cost analysis
    total_cost_usd: float
    cost_by_category: Dict[str, float]
    cost_by_location: Dict[str, float]
    most_expensive_item: str

    # Sourcing analysis
    max_shipping_days: int
    suppliers_needed: int
    single_source_risks: List[str]
    local_vs_online_pct: tuple  # (local%, online%)

    # Thermal analysis
    server_heat_output_w: float
    heat_recovered_w: float
    heat_losses_w: Dict[str, float]
    net_thermal_balance_w: float
    equilibrium_temp_c: float
    thermal_recommendation: str

    # Aquaculture analysis
    species: str
    optimal_temp_c: float
    temp_margin_to_stress_c: float
    max_stocking_kg: float
    estimated_yield_kg_per_year: float
    feed_cost_usd_per_year: float

    # ROI
    roi_months: float
    break_even_kg: float
    break_even_analysis: str

    # Risk register
    risks: List[Dict[str, Any]]

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_build(profile: BuildProfile) -> BuildAnalysisReport:
    """Generate a full engineering and sourcing report for a build profile."""
    compute = profile.compute_total()

    # Cost by category
    cost_by_cat = {}
    for item in ALL_ITEMS:
        idx = profile.item_selections.get(item.part_number, 0)
        opt = item.options[idx] if idx < len(item.options) else item.options[0]
        cost_by_cat[item.category] = cost_by_cat.get(item.category, 0) + opt.unit_price_usd * item.qty

    # Most expensive item
    most_expensive = max(compute["items"], key=lambda x: x["extended"])

    # Single-source risks (items with only 1 or 2 options)
    single_source = []
    for item in ALL_ITEMS:
        if len(item.options) <= 2:
            single_source.append(f"{item.part_number} — only {len(item.options)} source(s)")

    # Local vs online split
    local_total = sum(v for k, v in compute["by_location"].items() if "Chengdu" in k or "Local" in k)
    online_total = compute["total_usd"] - local_total
    local_pct = round(100 * local_total / compute["total_usd"], 1) if compute["total_usd"] > 0 else 0
    online_pct = round(100 * online_total / compute["total_usd"], 1) if compute["total_usd"] > 0 else 0

    # Thermal analysis
    te = ThermalEngineering()
    net_balance = te.heat_recovered_w - te.grow_bed_heat_loss_w - te.evap_cooling_w - te.makeup_cooling_w - te.earth_berm_loss_w()
    equilibrium = te.ambient_earth_temp_c + (te.heat_recovered_w / (te.earth_berm_u_value * te.tank_surface_area_m2 + 50))  # simplified

    if net_balance > 100:
        thermal_rec = f"NET POSITIVE (+{net_balance:.0f}W). System will warm. No backup heaters needed. Monitor grow bed temps — they may run hot."
    elif net_balance > -100:
        thermal_rec = f"NEAR BALANCE ({net_balance:.0f}W). System stable. Backup heaters recommended for cold nights."
    else:
        thermal_rec = f"NET NEGATIVE ({net_balance:.0f}W). System will cool. Must add backup heaters OR insulate grow beds OR pre-heat return water."

    # Aquaculture
    aqua = AquacultureSpec()
    max_stock = 40.0 * 10.0  # 40 kg/m³ × 10 m³ total volume
    # 2 harvest cycles per year (180 days each)
    annual_yield = max_stock * 2
    # Feed: 2% body weight/day × 365 × avg 20kg stock × $2/kg feed
    feed_cost = 0.02 * 20 * 365 * 2.0

    # ROI
    # Tilapia market price ~$6/kg wholesale
    revenue = annual_yield * 6.0
    net_profit = revenue - feed_cost
    roi_months = (compute["total_usd"] / net_profit) * 12 if net_profit > 0 else 999.9
    break_even_kg = compute["total_usd"] / 6.0  # kg of fish to sell at $6/kg to recover build cost

    # Risk register
    risks = []
    if "AliExpress" in str(compute["by_supplier"]) or any("AliExpress" in i["supplier"] for i in compute["items"]):
        risks.append({"level": "HIGH", "category": "Quality", "description": "AliExpress clone parts detected. Verify pH/DO probe authenticity before submersion. Fake Atlas probes will drift and kill fish."})
    if any("Pinduoduo" in i["supplier"] for i in compute["items"]):
        risks.append({"level": "HIGH", "category": "Quality", "description": "Pinduoduo ultra-cheap parts detected. High failure rate expected. Budget for replacements and test every component before deployment."})
    if any("1688" in i["supplier"] for i in compute["items"]):
        risks.append({"level": "MEDIUM", "category": "Sourcing", "description": "1688 wholesale sourcing requires bulk MOQs. Verify minimum order quantities match your build size."})
    if compute["max_shipping_days"] > 20:
        risks.append({"level": "MEDIUM", "category": "Schedule", "description": f"Longest shipping time is {compute['max_shipping_days']} days. Build cannot start until all parts arrive."})
    if net_balance < -50:
        risks.append({"level": "HIGH", "category": "Thermal", "description": f"Net thermal loss of {net_balance:.0f}W. Without backup heat, water will drop below tilapia minimum ({aqua.cold_stress_c}°C) in cold weather."})
    if local_pct < 20 and "Chengdu" in profile.name:
        risks.append({"level": "MEDIUM", "category": "Sourcing", "description": "Chengdu local profile but many items sourced online. Consider local alternatives for wire, enclosures, and pumps."})
    risks.append({"level": "LOW", "category": "Electrical", "description": "All 120V circuits near water must be GFCI-protected. Verify local electrical code compliance."})

    return BuildAnalysisReport(
        profile_name=profile.name,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        total_cost_usd=round(compute["total_usd"], 2),
        cost_by_category={k: round(v, 2) for k, v in cost_by_cat.items()},
        cost_by_location={k: round(v, 2) for k, v in compute["by_location"].items()},
        most_expensive_item=f"{most_expensive['part_number']} ({most_expensive['supplier']}) — ${most_expensive['extended']:.2f}",
        max_shipping_days=compute["max_shipping_days"],
        suppliers_needed=len(compute["by_supplier"]),
        single_source_risks=single_source,
        local_vs_online_pct=(local_pct, online_pct),
        server_heat_output_w=te.total_server_heat_w,
        heat_recovered_w=te.heat_recovered_w,
        heat_losses_w={
            "grow_beds": te.grow_bed_heat_loss_w,
            "evaporation": te.evap_cooling_w,
            "makeup_water": te.makeup_cooling_w,
            "earth_berm": te.earth_berm_loss_w(),
        },
        net_thermal_balance_w=round(net_balance, 1),
        equilibrium_temp_c=round(equilibrium, 1),
        thermal_recommendation=thermal_rec,
        species=aqua.species,
        optimal_temp_c=aqua.optimal_temp_c,
        temp_margin_to_stress_c=round(aqua.stress_threshold_c - equilibrium, 1),
        max_stocking_kg=max_stock,
        estimated_yield_kg_per_year=annual_yield,
        feed_cost_usd_per_year=round(feed_cost, 2),
        roi_months=round(roi_months, 1),
        break_even_kg=round(break_even_kg, 1),
        break_even_analysis=f"At ${revenue:.0f}/year revenue and ${feed_cost:.0f}/year feed cost, net profit is ${net_profit:.0f}/year. Build pays for itself in {roi_months:.1f} months. Need to sell {break_even_kg:.0f} kg to break even.",
        risks=risks,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION E: AQUACULTURE & THERMAL ENGINEERING (unchanged from v1)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AquacultureSpec:
    """Real tilapia aquaculture parameters from FAO and extension office data."""
    species: str = "Oreochromis niloticus (Nile Tilapia)"
    optimal_temp_c: float = 28.0
    lethal_max_c: float = 36.0
    lethal_min_c: float = 12.0
    stress_threshold_c: float = 32.0
    cold_stress_c: float = 20.0
    max_density_kg_m3: float = 60.0
    recommended_density_kg_m3: float = 40.0
    optimal_ph: tuple = (6.5, 8.5)
    lethal_ph: tuple = (4.0, 11.0)
    optimal_do_mg_l: float = 5.0
    min_do_mg_l: float = 3.0
    lethal_do_mg_l: float = 1.5
    optimal_nh3_mg_l: float = 0.05
    max_nh3_mg_l: float = 0.5
    optimal_no2_mg_l: float = 0.1
    max_no2_mg_l: float = 1.0
    feed_rate_pct_body_weight: float = 2.0
    feed_protein_pct: float = 32.0
    days_to_harvest: int = 180
    growth_rate_g_day: float = 2.7


@dataclass
class HydroponicSpec:
    """Real hydroponic parameters for raft/DWC system paired with tilapia."""
    system_type: str = "Deep Water Culture (DWC) / Raft"
    optimal_temp_c: float = 22.0
    acceptable_temp_c: tuple = (18.0, 26.0)
    ec_ms_cm: float = 1.8
    ph: tuple = (5.5, 6.5)
    recommended_crops: List[str] = field(default_factory=lambda: [
        "Lettuce (Lactuca sativa) — 28-day cycle",
        "Basil (Ocimum basilicum) — 21-day cycle",
        "Swiss Chard (Beta vulgaris) — 35-day cycle",
        "Bok Choy (Brassica rapa) — 30-day cycle",
        "Watercress (Nasturtium officinale) — 21-day cycle",
    ])
    bed_depth_cm: float = 30.0
    plant_spacing_cm: float = 20.0
    biofilm_surface_area_m2_m3: float = 300.0


@dataclass
class ThermalEngineering:
    """Real heat transfer calculations for the server-farm-to-aquaculture loop."""
    total_server_heat_w: float = 2600.0
    hex_efficiency: float = 0.75
    heat_recovered_w: float = 1950.0
    total_water_volume_l: float = 10000.0
    water_specific_heat_j_kg_k: float = 4186.0
    temp_rise_per_hour_c: float = 0.168
    earth_berm_u_value: float = 0.05
    tank_surface_area_m2: float = 33.0
    ambient_earth_temp_c: float = 15.0
    evap_cooling_w: float = 28.0
    makeup_cooling_w: float = 18.0
    grow_bed_heat_loss_w: float = 1920.0

    def earth_berm_loss_w(self) -> float:
        return self.earth_berm_u_value * self.tank_surface_area_m2 * (28 - self.ambient_earth_temp_c)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION F: WIRING SCHEMATIC — PROPER BOX-DRAWING ASCII
# ═══════════════════════════════════════════════════════════════════════════

WIRING_SCHEMATIC = r"""
+==============================================================================+
|                        ORBSTUDIO WIRING SCHEMATIC v2.0                       |
|                   ESP32-DevKitC-32E Controller #1 -- TANKS                   |
+==============================================================================+
|                                                                              |
|   ESP32 GPIO        CONNECTS TO                  WIRE GAUGE    NOTES         |
|   ----------        ----------                   ---------    ------         |
|   3.3V  --------->  DS18B20 VCC (x3 sensors)     22 AWG       1-Wire bus    |
|   GND   --------->  DS18B20 GND (x3)             22 AWG       Common GND    |
|   GPIO4 --------->  DS18B20 DATA (x3, parallel)  22 AWG       4.7k pull-up  |
|   3.3V  --------->  DHT22 VCC                    22 AWG       Air sensor    |
|   GND   --------->  DHT22 GND                    22 AWG                     |
|   GPIO5 --------->  DHT22 DATA                   22 AWG       10k pull-up   |
|   3.3V  --------->  Atlas EZO-pH VCC             22 AWG       I2C addr 0x63 |
|   GND   --------->  Atlas EZO-pH GND             22 AWG                     |
|   GPIO21--------->  Atlas EZO-pH SDA             22 AWG       I2C SDA       |
|   GPIO22--------->  Atlas EZO-pH SCL             22 AWG       I2C SCL       |
|   3.3V  --------->  Atlas EZO-DO VCC             22 AWG       I2C addr 0x61 |
|   GND   --------->  Atlas EZO-DO GND             22 AWG                     |
|   GPIO21--------->  Atlas EZO-DO SDA             22 AWG       Shared SDA    |
|   GPIO22--------->  Atlas EZO-DO SCL             22 AWG       Shared SCL    |
|   5V    --------->  Relay Module VCC             18 AWG       8-ch relay    |
|   GND   --------->  Relay Module GND             18 AWG                     |
|   GPIO12--------->  Relay 1 (Circulation Pump)   22 AWG       Active LOW    |
|   GPIO13--------->  Relay 2 (Aeration Pump)      22 AWG       Active LOW    |
|   GPIO14--------->  Relay 3 (Heater Backup)      22 AWG       Active LOW    |
|   GPIO15--------->  Relay 4 (Solenoid Valve)      22 AWG       Active LOW    |
|   GPIO16--------->  Relay 5 (Spare)              22 AWG                     |
|   GPIO17--------->  Relay 6 (Spare)              22 AWG                     |
|   GPIO18--------->  Relay 7 (Spare)              22 AWG                     |
|   GPIO19--------->  Relay 8 (Spare)              22 AWG                     |
|                                                                              |
|   POWER: 120V AC --> MEAN WELL LRS-50-5 --> 5V DC --> ESP32 + Relays + Sens|
|          15A breaker on Main Panel. GFCI required for wet locations.         |
|                                                                              |
+==============================================================================+

+==============================================================================+
|                     HEAT EXCHANGER PLUMBING DIAGRAM                          |
|                                                                              |
|    SERVER ROOM                   HEAT EXCHANGER              AQUACULTURE     |
|    -----------                   --------------              -----------     |
|                                                                              |
|  +---------+    Hot Glycol     +-----------+    Warm Water   +---------+   |
|  | Rack 01 |-----(45C)-------->|           |-----(35C)----->>|  Tank   |   |
|  | Rack 02 |-----(45C)-------->|  Plate HX |                 |  Alpha  |   |
|  | Rack 03 |-----(45C)-------->|  30-plate |-----(35C)----->>|  Tank   |   |
|  | Rack 04 |-----(45C)-------->|  316L SS  |                 |  Beta   |   |
|  +---------+                   +-----------+                 +---------+   |
|       |                             |                             |          |
|       | Cool Glycol                 | Cool Water                  |          |
|       | (35C)                       | (28C)                       |          |
|       v                             v                             v          |
|  +---------+                   +-----------+                 +---------+   |
|  |  Pump   |<------------------|  Sump     |<----------------| Grow    |   |
|  | (Glycol)|                   |  Tank     |                 | Beds    |   |
|  +---------+                   +-----------+                 +---------+   |
|                                                                              |
|  GLYCOL LOOP: 50/50 propylene glycol + distilled water + inhibitor           |
|  AQUA LOOP:   Fish tank water (no glycol -- direct contact)                  |
|  COUNTER-FLOW: Glycol inlet opposite water inlet for maximum delta-T         |
|                                                                              |
+==============================================================================+

+==============================================================================+
|                         ESP32 #2 -- GROW BEDS                                |
+==============================================================================+
|   GPIO4  --> DS18B20 DATA (water temp, grow bed north)                       |
|   GPIO5  --> DS18B20 DATA (water temp, grow bed south)                       |
|   GPIO18 --> DHT22 DATA (air temp + humidity, grow bed north)                |
|   GPIO19 --> DHT22 DATA (air temp + humidity, grow bed south)                |
|   GPIO12 --> Relay 1 (Grow bed circulation pump)                             |
|   GPIO13 --> Relay 2 (LED grow light -- 12V DC)                              |
|                                                                              |
+==============================================================================+

+==============================================================================+
|                         ESP32 #3 -- SERVER ROOM                              |
+==============================================================================+
|   GPIO4  --> DS18B20 DATA (server exhaust temp)                              |
|   GPIO5  --> DS18B20 DATA (glycol return temp)                               |
|   GPIO18 --> DHT22 DATA (server room ambient)                                |
|   GPIO12 --> Relay 1 (Server rack fan speed -- PWM)                          |
|   GPIO13 --> Relay 2 (Glycol pump)                                           |
|   GPIO14 --> Relay 3 (Emergency server shutdown signal)                      |
|                                                                              |
+==============================================================================+

+==============================================================================+
|                         ESP32 #4 -- FILTRATION & FLOW                        |
+==============================================================================+
|   GPIO4  --> DS18B20 DATA (sump tank temp)                                   |
|   GPIO5  --> YF-S201 FLOW SENSOR (pulse counter -- primary loop)             |
|   GPIO18 --> YF-S201 FLOW SENSOR (pulse counter -- backup loop)              |
|   GPIO12 --> Relay 1 (Biofilter air pump)                                    |
|   GPIO13 --> Relay 2 (Backup circulation pump)                               |
|   GPIO14 --> Relay 3 (Drain solenoid valve)                                  |
|   GPIO15 --> Relay 4 (Make-up water solenoid)                                |
|                                                                              |
+==============================================================================+

NETWORK: All 4x ESP32 connect to WiFi mesh --> Raspberry Pi 5 MQTT broker
         Pi 5 runs FastAPI backend + InfluxDB time-series DB
         Pi 5 connects to router via Ethernet (CAT6, PoE+ HAT)
"""


# ═══════════════════════════════════════════════════════════════════════════
# SECTION G: HARDWARE ABSTRACTION & MANIFEST
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PhysicalZone:
    """Bridge between thermal model and physical sensors/relays."""
    zone_id: str
    sim_temp_c: float = 24.0
    sim_heat_input_w: float = 0.0
    sim_heat_loss_w: float = 0.0
    ds18b20_address: Optional[str] = None
    dht22_gpio: Optional[int] = None
    ph_ezo_address: Optional[int] = None
    do_ezo_address: Optional[int] = None
    flow_pulse_gpio: Optional[int] = None
    pump_relay_gpio: Optional[int] = None
    aeration_relay_gpio: Optional[int] = None
    heater_relay_gpio: Optional[int] = None
    valve_relay_gpio: Optional[int] = None
    last_sensor_read: Optional[Dict] = None
    last_read_time: float = 0.0
    sensor_status: str = "unknown"


def get_manifest_with_selections(selections: Optional[Dict[str, int]] = None) -> dict:
    """Return the full BOM with optional per-item supplier selections."""
    if selections is None:
        selections = {}
    items = []
    total = 0.0
    for item in ALL_ITEMS:
        d = item.to_dict(selections.get(item.part_number, 0))
        total += d["extended_price_usd"]
        items.append(d)
    return {
        "items": items,
        "total_usd": round(total, 2),
        "item_count": len(items),
        "category_breakdown": _category_breakdown(items),
    }


def _category_breakdown(items: List[dict]) -> dict:
    cats = {}
    for item in items:
        cats[item["category"]] = cats.get(item["category"], 0) + item["extended_price_usd"]
    return {k: round(v, 2) for k, v in cats.items()}


def get_build_profiles() -> list:
    """Return all pre-defined build profiles with their computed totals."""
    return [
        {
            "id": p.name.lower().replace(" ", "_"),
            "name": p.name,
            "description": p.description,
            "icon": p.icon,
            "color": p.color,
            "strategy": p.strategy,
            "summary": p.compute_total(),
        }
        for p in ALL_PROFILES
    ]
