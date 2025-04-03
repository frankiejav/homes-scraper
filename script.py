import aiohttp
import asyncio
from bs4 import BeautifulSoup
import json
import time
import random
import os
import re
from urllib.parse import quote
from datetime import datetime
from typing import List, Dict, Any
import fake_useragent
import logging
import sys
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_random_headers() -> Dict[str, str]:
    """Generate random headers to avoid bot detection"""
    ua = fake_useragent.UserAgent()
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }

async def process_listing(session: aiohttp.ClientSession, listing: BeautifulSoup, location: str) -> Dict[str, Any]:
    try:
        # Try both price class variations and container types
        price_container = (
            listing.find('p', class_='price-container') or 
            listing.find('p', class_='price')
        )
        price_text = ''
        status = ''
        
        if price_container:
            # Get all text content first
            all_text = price_container.get_text(strip=True)
            
            # Extract price (it's usually the first part)
            # Split by any status text that might be appended
            price_parts = all_text.split()
            if price_parts:
                # Handle "Est" prices
                if price_parts[0] == 'Est' and len(price_parts) > 1:
                    price_text = price_parts[1]
                    status = 'Estimated Price'
                else:
                    # Take the first part as price, rest as status
                    price_text = price_parts[0]
                    if len(price_parts) > 1:
                        status = ' '.join(price_parts[1:])
            
            # Check for status tags
            status_tag = price_container.find('span', class_='status-pill')
            if status_tag:
                status = status_tag.get_text(strip=True)
        
        details_container = listing.find('ul', class_='detailed-info-container')
        beds = baths = sqft = None
        if details_container:
            for li in details_container.find_all('li'):
                text = li.text.strip()
                if 'Beds' in text:
                    try:
                        beds = int(text.split()[0])
                    except (ValueError, IndexError):
                        logger.debug(f"Could not parse beds from: {text}")
                elif 'Baths' in text:
                    try:
                        baths = float(text.split()[0])
                    except (ValueError, IndexError):
                        logger.debug(f"Could not parse baths from: {text}")
                elif 'Sq Ft' in text:
                    try:
                        sqft = int(text.split()[0].replace(',', ''))
                    except (ValueError, IndexError):
                        logger.debug(f"Could not parse sqft from: {text}")
        
        address = listing.find('p', class_='property-name')
        address_text = address.text.strip() if address else ''
        
        description_container = listing.find('div', class_='description-container')
        if description_container:
            agent_detail = description_container.find('p', class_='agent-detail')
            description = description_container.find('p', class_='property-description')
        else:
            agent_detail = listing.find('p', class_='agent-detail')
            description = listing.find('p', class_='property-description')
        
        agent = ''
        agency = ''
        if agent_detail:
            agent_name = agent_detail.find('span', class_='agent-name')
            agency_name = agent_detail.find('span', class_='agency-name')
            agent = agent_name.text.strip() if agent_name else ''
            agency = agency_name.text.strip() if agency_name else ''
        
        description_text = description.text.strip() if description else ''
        
        price_value = convert_price_to_number(price_text)
        
        # Only process properties worth $1.5 million or more
        if price_value < 1500000:
            return None
        
        # Format the property details
        property_details = {
            'Found high-value property:': '✓',
            'Address:': address_text,
            'Price:': price_text,
            'Price Value': price_value,
            'Status:': status if status else 'Not Listed For Sale',
            'Beds:': f"{beds}, Baths: {baths}, Sq Ft: {sqft}",
            'Agent:': agent,
            'Agency:': agency
        }
        
        # Log the formatted details
        for key, value in property_details.items():
            logger.info(f"{key} {value}")
        
        return property_details
    except AttributeError as e:
        logger.error(f"Couldn't extract all data from a listing: {e}")
        logger.debug(f"Listing HTML: {listing.prettify()}")
    except Exception as e:
        logger.error(f"Error processing listing: {e}")
        logger.debug(f"Listing HTML: {listing.prettify()}")
    return None

async def scrape_page(session: aiohttp.ClientSession, url: str, location: str) -> List[Dict[str, Any]]:
    max_retries = 1  # Reduced to 1 retry
    retry_delay = 2  # Reduced to 2 seconds
    
    for attempt in range(max_retries):
        try:
            session.headers.update(get_random_headers())
            
            async with session.get(url) as response:
                if response.status == 403:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return []
                
                if response.status != 200:
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for all listing containers - both for-sale and off-market
                listing_elements = (
                    soup.find_all('div', class_='for-sale-content-container') +
                    soup.find_all('div', class_='off-market-content-container')
                )
                
                if not listing_elements:
                    nosnippet_divs = soup.find_all('div', attrs={'data-nosnippet': True})
                    if nosnippet_divs:
                        listing_elements = nosnippet_divs
                    else:
                        return []
                
                # Process listings concurrently with a semaphore to limit concurrent tasks
                semaphore = asyncio.Semaphore(10)  # Increased from 5 to 10 concurrent tasks
                async def process_with_semaphore(listing):
                    async with semaphore:
                        return await process_listing(session, listing, location)
                
                tasks = [process_with_semaphore(listing) for listing in listing_elements]
                results = await asyncio.gather(*tasks)
                
                return [listing for listing in results if listing is not None]
                
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                continue
            return []
    
    return []

async def scrape_real_estate_listings(location: str, output_file: str = 'output.json') -> List[Dict[str, Any]]:
    properties = []
    page = 1
    
    # Parse location to handle neighborhoods correctly
    location_parts = location.strip().lower().split('/')
    
    if len(location_parts) > 1:
        # This is a neighborhood format: "city-state/neighborhood-name"
        city_state = location_parts[0]
        neighborhood = location_parts[1]
        # Format: https://www.homes.com/san-diego-ca/la-jolla-village-neighborhood/all-inventory/
        base_url = f"https://www.homes.com/{city_state}/{neighborhood}-neighborhood/all-inventory"
    else:
        # Standard city format
        formatted_location = location.strip().lower().replace(' ', '-')
        base_url = f"https://www.homes.com/{formatted_location}/all-inventory"
    
    # Load existing data if output file exists
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                # Ensure we have a list of properties
                if isinstance(existing_data, list):
                    properties = existing_data
                    logger.info(f"Loaded {len(properties)} existing records from {output_file}")
                else:
                    logger.warning(f"Existing {output_file} is not in the correct format, starting fresh")
        except json.JSONDecodeError:
            logger.warning(f"Could not parse existing {output_file}, starting fresh")
    
    headers = get_random_headers()
    async with aiohttp.ClientSession(headers=headers) as session:
        # First, get the total number of pages
        try:
            async with session.get(base_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    search_results = soup.find('p', class_='search-results')
                    if search_results:
                        page_info = search_results.find('span')
                        if page_info:
                            total_pages = int(page_info.text.split('of')[1].strip())
                            logger.info(f"Found {total_pages} total pages to scrape")
                        else:
                            total_pages = 1
                            logger.warning("Could not determine total pages, defaulting to 1")
                    else:
                        total_pages = 1
                        logger.warning("No search results element found, defaulting to 1 page")
                else:
                    total_pages = 1
                    logger.warning(f"Initial page request returned status {response.status}, defaulting to 1 page")
        except Exception as e:
            logger.error(f"Error getting total pages: {e}")
            total_pages = 1
        
        total_records_scraped = len(properties)
        logger.info(f"Starting with {total_records_scraped} existing records. Target: {total_pages} pages")
        
        while page <= total_pages:
            # Handle URL formatting for neighborhoods correctly
            if page > 1:
                # For pagination, neighborhood URLs use a different format
                # Check if it's a neighborhood URL
                if "neighborhood" in base_url:
                    # Remove trailing slash if exists
                    base_url_clean = base_url.rstrip('/')
                    current_url = f"{base_url_clean}/p{page}/"
                else:
                    current_url = f"{base_url}/p{page}/"
            else:
                current_url = f"{base_url}/"
            
            logger.info(f"Scraping page {page}/{total_pages}: {current_url}")
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            try:
                async with session.get(current_url) as response:
                    if response.status == 404:
                        logger.error(f"Page {page} not found (404). Stopping.")
                        break
                    
                    if response.status != 200:
                        logger.error(f"Page {page} returned unexpected status code: {response.status}. Stopping.")
                        break
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Check if we're on a valid page
                    error_container = soup.find('div', class_='error-container')
                    if error_container:
                        logger.error(f"Error container found on page {page}. Stopping.")
                        break
                    
                    # Count listings before processing
                    listing_elements = (
                        soup.find_all('div', class_='for-sale-content-container') +
                        soup.find_all('div', class_='off-market-content-container')
                    )
                    
                    if not listing_elements:
                        nosnippet_divs = soup.find_all('div', attrs={'data-nosnippet': True})
                        if nosnippet_divs:
                            listing_elements = nosnippet_divs
                    
                    logger.info(f"Found {len(listing_elements)} listing elements on page {page}")
                    
                    # Get listings from current page
                    page_listings = await scrape_page(session, current_url, location)
                    
                    if page_listings:
                        # Add new listings to properties list
                        previous_count = len(properties)
                        properties.extend(page_listings)
                        new_count = len(properties)
                        
                        logger.info(f"Page {page}: Processed {len(page_listings)} listings, {new_count - previous_count} added to dataset")
                        total_records_scraped += (new_count - previous_count)
                        
                        # Save after each page
                        try:
                            with open(output_file, 'w', encoding='utf-8') as f:
                                json.dump(properties, f, ensure_ascii=False, indent=4)
                            logger.info(f"Saved {len(properties)} total records to {output_file} (Page {page}/{total_pages} complete)")
                        except Exception as e:
                            logger.error(f"Error saving to {output_file} after page {page}: {e}")
                            # Try to save to a backup file
                            try:
                                backup_file = f'{output_file}_backup_{int(time.time())}.json'
                                with open(backup_file, 'w', encoding='utf-8') as f:
                                    json.dump(properties, f, ensure_ascii=False, indent=4)
                                logger.info(f"Saved backup to {backup_file}")
                            except Exception as backup_error:
                                logger.error(f"Failed to save backup: {backup_error}")
                    else:
                        logger.warning(f"No listings processed on page {page}. Stopping.")
                        break
                    
                    # Check for next page
                    pagination = soup.find('div', class_='pagination')
                    if pagination:
                        next_button = pagination.find('a', class_='next-page')
                        if not next_button:
                            logger.info(f"No next page button found after page {page}. Stopping.")
                            break
                    else:
                        # If we don't find a pagination div, but we know there are multiple pages based on the search results,
                        # continue with the next page anyway
                        search_results = soup.find('p', class_='search-results')
                        if search_results and page < total_pages:
                            logger.info(f"No pagination element found, but continuing to next page based on search results info.")
                        else:
                            logger.warning(f"No pagination element found on page {page}. Stopping.")
                            break
                    
                    # Progress report
                    progress_percentage = (page / total_pages) * 100 if total_pages > 0 else 100
                    logger.info(f"Progress: {progress_percentage:.1f}% ({page}/{total_pages} pages, {total_records_scraped} total records)")
                    
                    page += 1
                    
            except Exception as e:
                logger.error(f"Error processing page {page}: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                break
    
    logger.info(f"Completed scraping {len(properties)} properties in {location}")
    logger.info(f"Processed {page-1} of {total_pages} pages in total")
    logger.info(f"Progress: {((page-1) / total_pages) * 100:.1f}% complete")
    return properties

def convert_price_to_number(price_text: str) -> float:
    """Convert price text to number"""
    price_text = price_text.strip().replace(',', '')
    
    if 'million' in price_text.lower() or 'm' in price_text.lower():
        pattern = r'[$£€]?\s*(\d+\.?\d*)\s*[mM](?:illion)?'
        match = re.search(pattern, price_text)
        if match:
            return float(match.group(1)) * 1000000
    
    numbers = re.findall(r'[\d.]+', price_text)
    if numbers:
        return float(''.join(numbers))
    
    return 0

async def main():
    try:
        if not os.path.exists('input.txt'):
            logger.error("Error: input.txt file not found.")
            return
        
        all_properties = []
        output_file = 'output.json'
        
        # Check if output file exists and load any existing data
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    all_properties = json.load(f)
                    logger.info(f"Loaded {len(all_properties)} existing records from {output_file}")
            except json.JSONDecodeError:
                logger.warning(f"Could not parse existing {output_file}, starting fresh")
        
        with open('input.txt', 'r') as file:
            locations = file.readlines()
        
        logger.info(f"Found {len(locations)} locations to process")
        logger.info("Price filtering enabled: Only saving properties worth $1.5 million or more")
        
        for location in locations:
            location = location.strip()
            if location:
                logger.info(f"Processing location: {location}")
                properties = await scrape_real_estate_listings(location, output_file)
                
                # Only add properties if they aren't already saved
                if not os.path.exists(output_file):
                    all_properties.extend(properties)
                    # Save the combined results
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(all_properties, f, ensure_ascii=False, indent=4)
                
                await asyncio.sleep(random.uniform(1, 2))
        
        logger.info(f"\nTotal records scraped: {len(all_properties)}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise