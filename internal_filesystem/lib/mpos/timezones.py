# Converted from zones.csv using csv_to_py.py
# and then asked an LLM to shorten the list (otherwise it's a huge scroll)
# by keeping only the commonly used cities.

TIMEZONE_MAP = {
    "Africa/Abidjan": "GMT0",  # West Africa, GMT0
    "Africa/Accra": "GMT0",  # Ghana’s capital
    "Africa/Addis_Ababa": "EAT-3",  # Ethiopia’s capital
    "Africa/Algiers": "CET-1",  # Algeria’s capital
    "Africa/Bamako": "GMT0",  # Mali’s capital
    "Africa/Bangui": "WAT-1",  # Central African Republic’s capital
    "Africa/Brazzaville": "WAT-1",  # Republic of Congo’s capital
    "Africa/Cairo": "EET-2EEST,M4.5.5/0,M10.5.4/24",  # Egypt’s capital
    "Africa/Casablanca": "<+01>-1",  # Morocco’s major city
    "Africa/Dakar": "GMT0",  # Senegal’s capital
    "Africa/Dar_es_Salaam": "EAT-3",  # Tanzania’s major city
    "Africa/Djibouti": "EAT-3",  # Djibouti’s capital
    "Africa/Gaborone": "CAT-2",  # Botswana’s capital
    "Africa/Harare": "CAT-2",  # Zimbabwe’s capital
    "Africa/Johannesburg": "SAST-2",  # South Africa’s major city
    "Africa/Kampala": "EAT-3",  # Uganda’s capital
    "Africa/Khartoum": "CAT-2",  # Sudan’s capital
    "Africa/Kigali": "CAT-2",  # Rwanda’s capital
    "Africa/Kinshasa": "WAT-1",  # DRC’s capital
    "Africa/Lagos": "WAT-1",  # Nigeria’s major city
    "Africa/Libreville": "WAT-1",  # Gabon’s capital
    "Africa/Luanda": "WAT-1",  # Angola’s capital
    "Africa/Lusaka": "CAT-2",  # Zambia’s capital
    "Africa/Maputo": "CAT-2",  # Mozambique’s capital
    "Africa/Maseru": "SAST-2",  # Lesotho’s capital
    "Africa/Mbabane": "SAST-2",  # Eswatini’s capital
    "Africa/Mogadishu": "EAT-3",  # Somalia’s capital
    "Africa/Nairobi": "EAT-3",  # Kenya’s capital
    "Africa/Ndjamena": "WAT-1",  # Chad’s capital
    "Africa/Tripoli": "EET-2",  # Libya’s capital
    "Africa/Tunis": "CET-1",  # Tunisia’s capital
    "Africa/Windhoek": "CAT-2",  # Namibia’s capital
    "America/Anchorage": "AKST9AKDT,M3.2.0,M11.1.0",  # Alaska’s major city
    "America/Argentina/Buenos_Aires": "<-03>3",  # Argentina’s capital
    "America/Asuncion": "<-04>4<-03>,M10.1.0/0,M3.4.0/0",  # Paraguay’s capital
    "America/Belize": "CST6",  # Belize’s capital
    "America/Bogota": "<-05>5",  # Colombia’s capital
    "America/Boise": "MST7MDT,M3.2.0,M11.1.0",  # US, Idaho’s major city
    "America/Campo_Grande": "<-04>4",  # Brazil, Mato Grosso do Sul
    "America/Cancun": "EST5",  # Mexico’s major city
    "America/Caracas": "<-04>4",  # Venezuela’s capital
    "America/Cayenne": "<-03>3",  # French Guiana’s capital
    "America/Chicago": "CST6CDT,M3.2.0,M11.1.0",  # US, major city for CST
    "America/Costa_Rica": "CST6",  # Costa Rica’s capital
    "America/Denver": "MST7MDT,M3.2.0,M11.1.0",  # US, major city for MST
    "America/Detroit": "EST5EDT,M3.2.0,M11.1.0",  # US, Michigan’s major city
    "America/Edmonton": "MST7MDT,M3.2.0,M11.1.0",  # Canada, Alberta’s major city
    "America/El_Salvador": "CST6",  # El Salvador’s capital
    "America/Fortaleza": "<-03>3",  # Brazil, Northeast
    "America/Guatemala": "CST6",  # Guatemala’s capital
    "America/Guayaquil": "<-05>5",  # Ecuador’s major city
    "America/Guyana": "<-04>4",  # Guyana’s capital
    "America/Halifax": "AST4ADT,M3.2.0,M11.1.0",  # Canada, Atlantic time
    "America/Havana": "CST5CDT,M3.2.0/0,M11.1.0/1",  # Cuba’s capital
    "America/Indiana/Indianapolis": "EST5EDT,M3.2.0,M11.1.0",  # US, Indiana’s capital
    "America/Jamaica": "EST5",  # Jamaica’s capital
    "America/La_Paz": "<-04>4",  # Bolivia’s capital
    "America/Lima": "<-05>5",  # Peru’s capital
    "America/Los_Angeles": "PST8PDT,M3.2.0,M11.1.0",  # US, major city for PST
    "America/Manaus": "<-04>4",  # Brazil, Amazon region
    "America/Mexico_City": "CST6",  # Mexico’s capital
    "America/Montevideo": "<-03>3",  # Uruguay’s capital
    "America/Montreal": "EST5EDT,M3.2.0,M11.1.0",  # Canada, Quebec’s major city
    "America/Nassau": "EST5EDT,M3.2.0,M11.1.0",  # Bahamas’ capital
    "America/New_York": "EST5EDT,M3.2.0,M11.1.0",  # US, major city for EST
    "America/Panama": "EST5",  # Panama’s capital
    "America/Paramaribo": "<-03>3",  # Suriname’s capital
    "America/Phoenix": "MST7",  # US, Arizona’s major city
    "America/Port-au-Prince": "EST5EDT,M3.2.0,M11.1.0",  # Haiti’s capital
    "America/Puerto_Rico": "AST4",  # Puerto Rico’s major city
    "America/Recife": "<-03>3",  # Brazil, Pernambuco
    "America/Santiago": "<-04>4<-03>,M9.1.6/24,M4.1.6/24",  # Chile’s capital
    "America/Santo_Domingo": "AST4",  # Dominican Republic’s capital
    "America/Sao_Paulo": "<-03>3",  # Brazil’s major city
    "America/St_Johns": "NST3:30NDT,M3.2.0,M11.1.0",  # Canada, Newfoundland
    "America/Tegucigalpa": "CST6",  # Honduras’ capital
    "America/Toronto": "EST5EDT,M3.2.0,M11.1.0",  # Canada’s major city
    "America/Vancouver": "PST8PDT,M3.2.0,M11.1.0",  # Canada’s major city for PST
    "America/Winnipeg": "CST6CDT,M3.2.0,M11.1.0",  # Canada, Manitoba’s capital
    "Antarctica/McMurdo": "NZST-12NZDT,M9.5.0,M4.1.0/3",  # Major Antarctic base
    "Asia/Almaty": "<+05>-5",  # Kazakhstan’s major city
    "Asia/Amman": "<+03>-3",  # Jordan’s capital
    "Asia/Baghdad": "<+03>-3",  # Iraq’s capital
    "Asia/Baku": "<+04>-4",  # Azerbaijan’s capital
    "Asia/Bangkok": "<+07>-7",  # Thailand’s capital
    "Asia/Beirut": "EET-2EEST,M3.5.0/0,M10.5.0/0",  # Lebanon’s capital
    "Asia/Colombo": "<+0530>-5:30",  # Sri Lanka’s capital
    "Asia/Damascus": "<+03>-3",  # Syria’s capital
    "Asia/Dhaka": "<+06>-6",  # Bangladesh’s capital
    "Asia/Dubai": "<+04>-4",  # UAE’s major city
    "Asia/Hong_Kong": "HKT-8",  # Major global city
    "Asia/Irkutsk": "<+08>-8",  # Russia, Siberia
    "Asia/Jakarta": "WIB-7",  # Indonesia’s capital
    "Asia/Jerusalem": "IST-2IDT,M3.4.4/26,M10.5.0",  # Israel’s capital
    "Asia/Kabul": "<+0430>-4:30",  # Afghanistan’s capital
    "Asia/Karachi": "PKT-5",  # Pakistan’s major city
    "Asia/Kathmandu": "<+0545>-5:45",  # Nepal’s capital
    "Asia/Kolkata": "IST-5:30",  # India’s major city
    "Asia/Krasnoyarsk": "<+07>-7",  # Russia, Siberia
    "Asia/Kuala_Lumpur": "<+08>-8",  # Malaysia’s capital
    "Asia/Manila": "PST-8",  # Philippines’ capital
    "Asia/Muscat": "<+04>-4",  # Oman’s capital
    "Asia/Riyadh": "<+03>-3",  # Saudi Arabia’s capital
    "Asia/Seoul": "KST-9",  # South Korea’s capital
    "Asia/Shanghai": "CST-8",  # China’s major city
    "Asia/Singapore": "<+08>-8",  # Singapore’s global prominence
    "Asia/Taipei": "CST-8",  # Taiwan’s capital
    "Asia/Tashkent": "<+05>-5",  # Uzbekistan’s capital
    "Asia/Tbilisi": "<+04>-4",  # Georgia’s capital
    "Asia/Tehran": "<+0330>-3:30",  # Iran’s capital
    "Asia/Thimphu": "<+06>-6",  # Bhutan’s capital
    "Asia/Tokyo": "JST-9",  # Japan’s capital
    "Asia/Ulaanbaatar": "<+08>-8",  # Mongolia’s capital
    "Asia/Vladivostok": "<+10>-10",  # Russia’s Far East
    "Asia/Yakutsk": "<+09>-9",  # Russia, Siberia
    "Asia/Yekaterinburg": "<+05>-5",  # Russia, Ural region
    "Asia/Yerevan": "<+04>-4",  # Armenia’s capital
    "Atlantic/Azores": "<-01>1<+00>,M3.5.0/0,M10.5.0/1",  # Portugal’s autonomous region
    "Atlantic/Bermuda": "AST4ADT,M3.2.0,M11.1.0",  # Bermuda’s capital
    "Atlantic/Canary": "WET0WEST,M3.5.0/1,M10.5.0",  # Spain’s autonomous region
    "Atlantic/Cape_Verde": "<-01>1",  # Cape Verde’s capital
    "Atlantic/Reykjavik": "GMT0",  # Iceland’s capital
    "Atlantic/Stanley": "<-03>3",  # Falkland Islands’ capital
    "Australia/Adelaide": "ACST-9:30ACDT,M10.1.0,M4.1.0/3",  # Major city for +9:30
    "Australia/Brisbane": "AEST-10",  # Major city for +10
    "Australia/Darwin": "ACST-9:30",  # Major city for +9:30
    "Australia/Hobart": "AEST-10AEDT,M10.1.0,M4.1.0/3",  # Tasmania’s capital
    "Australia/Melbourne": "AEST-10AEDT,M10.1.0,M4.1.0/3",  # Major city for +10
    "Australia/Perth": "AWST-8",  # Major city for +8
    "Australia/Sydney": "AEST-10AEDT,M10.1.0,M4.1.0/3",  # Major city for +10 with DST
    "Europe/Amsterdam": "CET-1CEST,M3.5.0,M10.5.0/3",  # Netherlands’ capital
    "Europe/Athens": "EET-2EEST,M3.5.0/3,M10.5.0/4",  # Greece’s capital
    "Europe/Belgrade": "CET-1CEST,M3.5.0,M10.5.0/3",  # Serbia’s capital
    "Europe/Berlin": "CET-1CEST,M3.5.0,M10.5.0/3",  # Germany’s capital
    "Europe/Brussels": "CET-1CEST,M3.5.0,M10.5.0/3",  # Belgium’s capital
    "Europe/Bucharest": "EET-2EEST,M3.5.0/3,M10.5.0/4",  # Romania’s capital
    "Europe/Budapest": "CET-1CEST,M3.5.0,M10.5.0/3",  # Hungary’s capital
    "Europe/Copenhagen": "CET-1CEST,M3.5.0,M10.5.0/3",  # Denmark’s capital
    "Europe/Dublin": "IST-1GMT0,M10.5.0,M3.5.0/1",  # Ireland’s capital
    "Europe/Helsinki": "EET-2EEST,M3.5.0/3,M10.5.0/4",  # Finland’s capital
    "Europe/Istanbul": "<+03>-3",  # Turkey’s major city
    "Europe/Kiev": "EET-2EEST,M3.5.0/3,M10.5.0/4",  # Ukraine’s capital
    "Europe/Lisbon": "WET0WEST,M3.5.0/1,M10.5.0",  # Portugal’s capital
    "Europe/London": "GMT0BST,M3.5.0/1,M10.5.0",  # UK’s capital
    "Europe/Madrid": "CET-1CEST,M3.5.0,M10.5.0/3",  # Spain’s capital
    "Europe/Minsk": "<+03>-3",  # Belarus’ capital
    "Europe/Moscow": "MSK-3",  # Russia’s capital
    "Europe/Paris": "CET-1CEST,M3.5.0,M10.5.0/3",  # France’s capital
    "Europe/Prague": "CET-1CEST,M3.5.0,M10.5.0/3",  # Czech Republic’s capital
    "Europe/Riga": "EET-2EEST,M3.5.0/3,M10.5.0/4",  # Latvia’s capital
    "Europe/Rome": "CET-1CEST,M3.5.0,M10.5.0/3",  # Italy’s capital
    "Europe/Sofia": "EET-2EEST,M3.5.0/3,M10.5.0/4",  # Bulgaria’s capital
    "Europe/Stockholm": "CET-1CEST,M3.5.0,M10.5.0/3",  # Sweden’s capital
    "Europe/Tallinn": "EET-2EEST,M3.5.0/3,M10.5.0/4",  # Estonia’s capital
    "Europe/Vienna": "CET-1CEST,M3.5.0,M10.5.0/3",  # Austria’s capital
    "Europe/Warsaw": "CET-1CEST,M3.5.0,M10.5.0/3",  # Poland’s capital
    "Pacific/Auckland": "NZST-12NZDT,M9.5.0,M4.1.0/3",  # New Zealand’s major city
    "Pacific/Fiji": "<+12>-12",  # Fiji’s prominence
    "Pacific/Honolulu": "HST10",  # Hawaii’s major city
    "Pacific/Tahiti": "<-10>10",  # French Polynesia’s prominence
    "Etc/UTC": "UTC0",  # Standard UTC
    "Etc/GMT": "GMT0",  # Standard GMT
}
