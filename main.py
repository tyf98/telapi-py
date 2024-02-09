from fastapi import FastAPI, Response
from starlette.responses import StreamingResponse
from io import BytesIO
import requests
from PIL import Image
import segno
import logging
from fastapi.responses import JSONResponse
from staticmap import StaticMap, CircleMarker

app = FastAPI()

@app.get("/", response_class=Response)
def qrdemo(color: str = '#7A663C', logourl: str = "https://i0.wp.com/godofwealth.co/wp-content/uploads/2023/10/happy-chinese-new-year-2024-thumb.jpg"):
    # Open QR code image
    qr_image = Image.open(generate_qr('Hello World!', color)).convert('RGBA')  # Convert QR code to RGBA mode

    # Call the overlay_qr_code function with the desired percentage
    qr_image = overlay_qr_code(qr_image, fetch_logo(logourl), percentageOfQrCode)

    # Save result
    return save_result(qr_image)

@app.get("/qrcode", response_class=Response)
def qrdemo(data:str, color: str = '#7A663C', logourl: str ='https://www.sgcarmart.com/_next/image?url=https%3A%2F%2Fi.i-sgcm.com%2Fnews%2Farticle_news%2F2020%2F22464_3_l.jpg&w=1920&q=75'):
    # Open QR code image
    qr_image = Image.open(generate_qr(data, color)).convert('RGBA')  # Convert QR code to RGBA mode

    # Call the overlay_qr_code function with the desired percentage
    qr_image = overlay_qr_code(qr_image, fetch_logo(logourl), percentageOfQrCode)

    # Save result
    return save_result(qr_image)

@app.get("/generate_map")
def generate_map(deviceLat: float, deviceLon: float):
    # Create a new static map
    m = StaticMap(200, 200)

    # Create a marker for the device location
    marker = CircleMarker((deviceLon, deviceLat), 'red', 12)

    # Add the marker to the map
    m.add_marker(marker)

    # Render the map to an image
    image = m.render()

    # Save result
    return save_result(image)

@app.get("/vcard", response_class=Response)
def vcard_qr(first_name: str, last_name: str, organisation: str, title: str, email: str, phone: str, street: str, city: str, state: str, country: str, postal: str, website: str, color: str = '#7A663C', logourl: str = 'https://www.sgcarmart.com/_next/image?url=https%3A%2F%2Fi.i-sgcm.com%2Fnews%2Farticle_news%2F2020%2F22464_3_l.jpg&w=1920&q=75'):
    # Generate vCard data manually
    vcard_data = f'BEGIN:VCARD\nVERSION:3.0\nN:{last_name};{first_name}\nFN:{first_name} {last_name}\nORG:{organisation}\nTITLE:{title}\nEMAIL:{email}\nTEL;TYPE=cell:{phone}\nADR;TYPE=Work:;;{street};{city};{state};{postal};{country}\nURL:{website}\nEND:VCARD'

    # Open QR code image
    qr_image = Image.open(generate_qr(vcard_data, color)).convert('RGBA')  # Convert QR code to RGBA mode

    # Call the overlay_qr_code function with the desired percentage
    qr_image = overlay_qr_code(qr_image, fetch_logo(logourl), percentageOfQrCode)
    
    # Save result
    return save_result(qr_image)

##### Functions and Variables #####
percentageOfQrCode = 0.3
def generate_qr(data: str, color: str = '#000000'):
    # Generate QR code
    qr = segno.make_qr(data, error='h')
    qr_buffer = BytesIO()
    qr.save(qr_buffer, kind='png', scale=32, border = 1, dark=color)
    qr_buffer.seek(0)
    return qr_buffer

def overlay_qr_code(qr_image, overlay_image, percentageOfQrCode):
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

    # Return the modified qr_image
    return qr_image

def fetch_logo(logourl: str):
    # Download overlay image from URL
    try:
        response = requests.get(logourl)
    except requests.exceptions.RequestException as e:
        logging.error(f" Invalid URL or base64 image: {e}")
        return JSONResponse(content={"error": "Invalid URL or base64 image"})

    # Check if the URL points to an image
    if 'content-type' not in response.headers or 'image' not in response.headers['content-type']:
        logging.error("  URL does not point to an image")
        return JSONResponse(content={"error": "URL does not point to an image"})
    
    return Image.open(BytesIO(response.content)).convert('RGBA')  # Convert overlay image to RGBA mode
    
def save_result(qr_image: Image):
    # Save result
    result_buffer = BytesIO()
    qr_image.save(result_buffer, format='png')
    result_buffer.seek(0)

    return StreamingResponse(result_buffer, media_type="image/png")