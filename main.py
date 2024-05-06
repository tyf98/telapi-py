from fastapi import FastAPI, Response
from starlette.responses import StreamingResponse
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont
import segno
import logging
from staticmap import StaticMap, CircleMarker
from geopy.geocoders import Nominatim

app = FastAPI()

defaultLogo = "https://i.ibb.co/WPQSS4d/Corp-Rectangular.png"

@app.get("/", response_class=Response)
def qrdemo(color: str = '#7A663C', logourl: str = defaultLogo, percentageOfQrCode: float=0.7):
    # Open QR code image
    qr_image = Image.open(generate_qr('Hello World!', color)).convert('RGBA')  # Convert QR code to RGBA mode

    # Call the overlay_qr_code function with the desired percentage
    qr_image = overlay_qr_code(qr_image, fetch_logo(logourl), percentageOfQrCode)

    # Save result
    return save_result(qr_image)

@app.get("/qrcode", response_class=Response)
def qrcode(data:str, color: str = '#7A663C', logourl: str = defaultLogo, percentageOfQrCode: float=0.3, scdLabel: str | None = None):

    # Check if logourl is default
    if logourl == defaultLogo:
        percentageOfQrCode = 0.50

    # Open QR code image
    qr_image = Image.open(generate_qr(data, color)).convert('RGBA')  # Convert QR code to RGBA mode

    # Call the overlay_qr_code function with the desired percentage
    qr_image = overlay_qr_code(qr_image, fetch_logo(logourl), percentageOfQrCode, scdLabel)

    # Save result
    return save_result(qr_image)

@app.get("/staticmap")
def staticMap(deviceLat: float, deviceLon: float):
    # Create a new static map
    m = StaticMap(400, 400)

    # Create a marker for the device location
    marker = CircleMarker((deviceLon, deviceLat), 'red', 12)

    # Add the marker to the map
    m.add_marker(marker)

    # Render the map to an image
    image = m.render()

    # Save result
    return save_result(image)

@app.get("/get_address")
def get_address(deviceLat: float, deviceLon: float):
    
    geolocator = Nominatim(user_agent="Power_API")
    location = geolocator.reverse([deviceLat, deviceLon], exactly_one=True)
    address = location.raw['address']
    formatted_address = f"{address.get('house_number', '')} {address.get('road', '')}, {address.get('country', '')} {address.get('postcode', '')}"
    
    return formatted_address

##### Functions and Variables #####
def generate_qr(data: str, color: str = '#000000'):
    # Generate QR code
    qr = segno.make_qr(data, error='h')
    qr_buffer = BytesIO()
    qr.save(qr_buffer, kind='png', scale=32, border = 1, dark=color)
    qr_buffer.seek(0)
    return qr_buffer

def overlay_qr_code(qr_image, overlay_image, percentageOfQrCode, scdLabel=None):
    # Check if overlay_image is not None
    if overlay_image is None:
        logging.error("Overlay image is not available")
        return qr_image  # Return the original qr_image without overlay
        
    # Calculate size for overlay image (maintain aspect ratio)
    qr_code_size_without_border = qr_image.width - 4 * 2 * 32  # Subtract the size of the quiet zone
    overlay_size = int(qr_code_size_without_border * percentageOfQrCode)  # Change this line
    overlay_width = int(overlay_image.width * overlay_size / min(overlay_image.size))
    overlay_height = int(overlay_image.height * overlay_size / min(overlay_image.size))
    overlay_image = overlay_image.resize((overlay_width, overlay_height))

    # Calculate position for overlay image (centered)
    position = ((qr_image.width - overlay_width) // 2, (qr_image.height - overlay_height) // 2)

    # Overlay image on QR code
    qr_image.paste(overlay_image, position, overlay_image)  # Use overlay_image as mask for transparency

    if scdLabel is not None:
        logging.info("SCD Label is not none.")
        
        # Create ImageDraw object
        draw = ImageDraw.Draw(qr_image)

        # Specify font-size and type
        font_size = 30
        font = ImageFont.truetype("./arialbd.ttf", font_size)

        # Calculate width and height of the text to center it
        text_length = draw.textlength(scdLabel, font)

        # If the text is too wide for the overlay image, decrease the font size until it fits
        while text_length > overlay_width/2:
            font_size -= 1
            font = ImageFont.truetype("./arialbd.ttf", font_size)
            text_length = draw.textlength(scdLabel, font)

        # Calculate position for the text (centered horizontally, 10% from the bottom vertically)
        text_x = (qr_image.width - text_length) // 2
        text_y = position[1] + overlay_height - int(0.27 * overlay_height)

        # Apply text overlay
        draw.text((text_x, text_y), scdLabel, fill="#7A663C", font=font)
        

    # Return the modified qr_image
    return qr_image

def fetch_logo(logourl: str):
    # Download overlay image from URL
    try:
        response = requests.get(logourl)
    except requests.exceptions.RequestException as e:
        logging.error(f" Invalid URL or base64 image: {e}")
        logging.error(f" Response: {response.__dict__ if 'response' in locals() else 'No response'}")
        return None

    # Check if the URL points to an image
    if 'content-type' not in response.headers or not response.headers['content-type'].startswith('image'):
        logging.error("URL does not point to an image")
        logging.error(f" Response: {response.__dict__ if 'response' in locals() else 'No response'}")
        return None
    
    return Image.open(BytesIO(response.content)).convert('RGBA')  # Convert overlay image to RGBA mode
    
def save_result(qr_image: Image):
    # Save result
    result_buffer = BytesIO()
    qr_image.save(result_buffer, format='png')
    result_buffer.seek(0)

    return StreamingResponse(result_buffer, media_type="image/png")