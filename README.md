# Homes.com Property Scraper

A Python script for scraping real estate listings from Homes.com.

## Features

- Scrapes property listings from Homes.com by location
- Handles pagination automatically
- Works with both city searches and neighborhood-specific searches
- Filters properties by price (currently set to $1.5M+)
- Extracts details like price, beds, baths, square footage, agent info
- Saves results as JSON
- Resumes from previous scrape results

## Requirements

- Python 3.7+
- Required packages (listed in requirements.txt):
  - aiohttp
  - asyncio
  - beautifulsoup4
  - fake_useragent

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/frankiejav/homes-scraper.git
   cd homes-scraper
   ```

2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Create an `input.txt` file in the same directory as the script
2. Add locations to scrape, one per line. Examples:
   ```
   Beverly Hills, CA
   Malibu, CA
   ```
3. Run the script:
   ```bash
   python script.py
   ```

### Location Format

- For city searches: `City, State` (e.g., `Beverly Hills, CA`)
- For neighborhood searches: `City-State/Neighborhood` (e.g., `Los Angeles, CA/Bel Air`)

### Output

The script saves results to `output.json`. Each property is saved with these details:
- Address
- Price
- Status (For Sale, Sold, etc.)
- Beds, Baths, Square Footage
- Agent and Agency information

## Advanced Configuration

You can modify these parameters in the script:
- `price_value < 1500000` - Adjust the price filter threshold
- `max_retries` - Change the number of retry attempts
- `retry_delay` - Adjust wait time between retries
- `output_file` - Change the output filename

## Logging

The script logs progress and errors to:
- Console
- `scraper.log` file

## Notes

- The script uses random delays and user agents to avoid detection

## Disclaimer

This script is for educational purposes only. Use responsibly and in accordance with Homes.com's terms of service. 
