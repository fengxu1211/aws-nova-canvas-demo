import json
import io
import random
import gradio as gr
from PIL import Image
from generate import *
import numpy as np
from typing import Dict, Any
from processImage import process_and_encode_image, ENABLE_NSFW_CHECK
from datetime import datetime # Import datetime
import time
import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

client = boto3.client('logs')

def custom_log(message):
    # print(message)
    logger.info(message)
    # client.put_log_events(
    #     logGroupName='/aws/lambda/canvas-demo',
    #     logStreamName='custom-stream',
    #     logEvents=[{'timestamp': int(time.time() * 1000), 'message': message}]
    # )

def rgba_to_hex(rgba):
    custom_log(f"[{datetime.now()}] Running rgba_to_hex...")
    r, g, b, _ = [int(float(x)) for x in rgba[5:-1].split(',')]
    return f"#{r:02X}{g:02X}{b:02X}"

def add_color_to_list(current_colors, new_color):
    custom_log(f"[{datetime.now()}] Running add_color_to_list...")
    new_color_hex = rgba_to_hex(new_color)
    color_list = current_colors.split(',')
    if new_color_hex not in color_list and len(color_list) < 10:
        color_list.append(new_color_hex)
    return ','.join(filter(None, color_list))

def create_padded_image(image, padding_percent=100):
    custom_log(f"[{datetime.now()}] Running create_padded_image...")
    image = image['background']
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    width, height = image.size
    new_width = int(width * (1 + padding_percent/100))
    new_height = int(height * (1 + padding_percent/100))

    padded = Image.new('RGBA', (new_width, new_height), (255, 255, 255, 255))

    x_offset = (new_width - width) // 2
    y_offset = (new_height - height) // 2

    padded.paste(image, (x_offset, y_offset))
    custom_log(f"[{datetime.now()}] Finished create_padded_image.")
    return padded

def process_composite_to_mask(original_image, composite_image, transparent=False):
    custom_log(f"[{datetime.now()}] Running process_composite_to_mask...")
    original_array = np.array(original_image.convert('RGBA'))
    if transparent:
        custom_log(f"[{datetime.now()}] Processing in transparent mode (non-white to black)...")
        is_not_white_mask = ~((original_array[:, :, 0] == 255) &
                              (original_array[:, :, 1] == 255) &
                              (original_array[:, :, 2] == 255))
        output_image = Image.new('RGBA', original_image.size, (255, 255, 255, 255))
        output_array = np.array(output_image)
        output_array[is_not_white_mask] = [0, 0, 0, 255]
        result_image = Image.fromarray(output_array, mode='RGBA')
        custom_log(f"[{datetime.now()}] Finished process_composite_to_mask (transparent mode).")
        return result_image
    if composite_image is None:
        mask = np.full(original_array.shape[:2], 0, dtype=np.uint8)
        transparent_areas = original_array[:, :, 3] == 0
        mask[transparent_areas] = 255
    else:
        composite_array = np.array(composite_image.convert('RGBA'))

        difference = np.any(original_array != composite_array, axis=2)
        mask = np.full(original_array.shape[:2], 255, dtype=np.uint8)
        mask[difference] = 0

    custom_log(f"[{datetime.now()}] Finished process_composite_to_mask.")
    return Image.fromarray(mask, mode='L')

def build_request(task_type, params, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0, num_of_imgs:int=1):
    custom_log(f"[{datetime.now()}] Building request for task type: {task_type}")
    param_dict = {
        "TEXT_IMAGE": "textToImageParams",
        "INPAINTING": "inPaintingParams",
        "OUTPAINTING": "outPaintingParams",
        "IMAGE_VARIATION": "imageVariationParams",
        "COLOR_GUIDED_GENERATION": "colorGuidedGenerationParams",
        "BACKGROUND_REMOVAL": "backgroundRemovalParams"
    }
    custom_log(f"[{datetime.now()}] TASK_TYPE: {task_type}")
    custom_log(f"[{datetime.now()}] PARAM_DICT: {param_dict[task_type]}")
    custom_log(f"[{datetime.now()}] num_of_imgs: {num_of_imgs}")
    
    request_body = {
        "taskType": task_type,
        param_dict[task_type]: params,
        "imageGenerationConfig": {
            "numberOfImages": num_of_imgs,
            "height": height,
            "width": width,
            "quality": quality,
            "cfgScale": cfg_scale,
            "seed": seed
        }
    }
    
    custom_log(f"[{datetime.now()}] Finished building request.")
    return json.dumps(request_body)

def check_return(result):
    custom_log(f"[{datetime.now()}] Checking return value...")
    if isinstance(result, list) and len(result) > 0 and not isinstance(result[0], bytes):
        custom_log(f"[{datetime.now()}] Result is not bytes (likely error message): {result}")
        return None, gr.update(visible=True, value=result)

    custom_log(f"[{datetime.now()}] Result is bytes, opening image...")
    return [Image.open(io.BytesIO(img)) for img in result], gr.update(value=None,visible=False)


def text_to_image(prompt, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0, num_of_imgs=3):
    custom_log(f"[{datetime.now()}] --- text_to_image START ---")
    text_to_image_params = {"text": prompt,
                            **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
                            }

    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed, num_of_imgs)
    custom_log(f"[{datetime.now()}] Calling generate_image for TEXT_IMAGE...")
    result = generate_image(body)
    custom_log(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    custom_log(f"[{datetime.now()}] --- text_to_image END ---")
    return output


def inpainting(mask_image, mask_prompt=None, text=None, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    custom_log(f"[{datetime.now()}] --- inpainting START ---")
    custom_log(f"[{datetime.now()}] Processing background image...")
    global ENABLE_NSFW_CHECK
    ENABLE_NSFW_CHECK = True
    image = process_and_encode_image(mask_image['background'])
    if len(image) < 200:
        custom_log(f"[{datetime.now()}] Error processing background image: {image}")
        custom_log(f"[{datetime.now()}] --- inpainting END (Error) ---")
        return None, gr.update(visible=True, value=image)

    mask_image_encoded = None # Initialize

    # Prioritize mask_prompt
    if mask_prompt and mask_prompt.strip(): # Check if mask_prompt is not None and not just whitespace
        custom_log(f"[{datetime.now()}] Using mask_prompt, ignoring mask_image.")
    elif mask_image and isinstance(mask_image, dict) and 'composite' in mask_image:
        custom_log(f"[{datetime.now()}] Using mask_image, processing composite mask...")
        mask = process_composite_to_mask(mask_image['background'], mask_image['composite'])
        mask_image_encoded = process_and_encode_image(mask)
        if not mask_image_encoded or len(mask_image_encoded) < 200:
             custom_log(f"[{datetime.now()}] Error processing mask image: {mask_image_encoded}")
             custom_log(f"[{datetime.now()}] --- inpainting END (Error) ---")
             return None, gr.update(visible=True, value="Error processing mask image.")
        custom_log(f"[{datetime.now()}] Finished processing composite mask.")
    else:
        custom_log(f"[{datetime.now()}] Error: Neither maskPrompt nor a valid maskImage provided.")
        custom_log(f"[{datetime.now()}] --- inpainting END (Error) ---")
        raise ValueError("You must specify either maskPrompt or provide a maskImage with a composite layer.")

    custom_log(f"[{datetime.now()}] Inputs for in_painting_params:")
    if isinstance(image, str):
        custom_log(f"[{datetime.now()}] Inpainting Image first 50 characters of Image: {image[:50]}")
    if isinstance(mask_image_encoded, str):
        custom_log(f"[{datetime.now()}] Inpainting Image first 50 characters of Mask: {mask_image_encoded[:50]}")
    custom_log(f"[{datetime.now()}] mask_prompt: {mask_prompt}")
    custom_log(f"[{datetime.now()}] text: {text}")
    custom_log(f"[{datetime.now()}] negative_text: {negative_text}")  

    try:
        in_painting_params = {
            "image": image,
            **({"maskImage": mask_image_encoded} if mask_image_encoded not in [None, ""] else {}),
            **({"maskPrompt": mask_prompt} if mask_prompt not in [None, ""] else {}),
            **({"text": text} if text not in [None, ""] else {}),
            **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
        }
    except Exception as e:
        custom_log(f"[{datetime.now()}] Error constructing in_painting_params: {e}")
        return None, gr.update(visible=True, value=f"Error constructing in_painting_params: {e}")

    body = build_request("INPAINTING", in_painting_params, height, width, quality, cfg_scale, seed)
    custom_log(f"[{datetime.now()}] Calling generate_image for INPAINTING...")
    result = generate_image(body)
    custom_log(f"[{datetime.now()}] generate_image call finished.")
    images, errorbox = check_return(result)
    custom_log(f"[{datetime.now()}] --- inpainting END ---")
    return images[0], errorbox

def outpainting(mask_image, mask_prompt=None, text=None, negative_text=None, outpainting_mode="DEFAULT", height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    custom_log(f"[{datetime.now()}] --- outpainting START ---")
    custom_log(f"[{datetime.now()}] Processing background image...")
    global ENABLE_NSFW_CHECK
    ENABLE_NSFW_CHECK = True
    image = process_and_encode_image(mask_image['background'])
    if len(image) < 200:
        custom_log(f"[{datetime.now()}] Error processing background image: {image}")
        custom_log(f"[{datetime.now()}] --- outpainting END (Error) ---")
        return None, gr.update(visible=True, value=image)

    mask_image_encoded = None # Initialize

    # Prioritize mask_prompt
    if mask_prompt and mask_prompt.strip(): # Check if mask_prompt is not None and not just whitespace
        custom_log(f"[{datetime.now()}] Using mask_prompt, ignoring mask_image.")
        # mask_image_encoded remains None
    elif mask_image and isinstance(mask_image, dict) and 'composite' in mask_image:
        custom_log(f"[{datetime.now()}] Using mask_image, processing composite mask for outpainting...")
        mask = process_composite_to_mask(mask_image['background'], None) # Mask is original area
        image_with_alpha = process_composite_to_mask(mask_image['background'], None, True) # Image has alpha
        image = process_and_encode_image(image_with_alpha)
        mask_image_encoded = process_and_encode_image(mask)
        if not mask_image_encoded or len(mask_image_encoded) < 200:
             custom_log(f"[{datetime.now()}] Error processing mask image: {mask_image_encoded}")
             custom_log(f"[{datetime.now()}] --- outpainting END (Error) ---")
             return None, gr.update(visible=True, value="Error processing mask image.")
        custom_log(f"[{datetime.now()}] Finished processing composite mask for outpainting.")
    else:
        # Neither valid mask_prompt nor valid mask_image provided
        custom_log(f"[{datetime.now()}] Error: Neither maskPrompt nor a valid maskImage provided.")
        custom_log(f"[{datetime.now()}] --- outpainting END (Error) ---")
        raise ValueError("You must specify either maskPrompt or provide a maskImage with a composite layer.")


    custom_log(f"[{datetime.now()}] Inputs for out_painting_params:")
    if isinstance(image, str):
        custom_log(f"[{datetime.now()}] Outpainting Image first 50 characters of Image: {image[:50]}")
    if isinstance(mask_image_encoded, str):
        custom_log(f"[{datetime.now()}] Outpainting Image first 50 characters of Mask: {mask_image_encoded[:50]}")
    custom_log(f"[{datetime.now()}] mask_prompt: {mask_prompt}")
    custom_log(f"[{datetime.now()}] text: {text}")
    custom_log(f"[{datetime.now()}] negative_text: {negative_text}")  

    try:
        out_painting_params = {
            "image": image,
            "outPaintingMode": outpainting_mode,
            **({"maskImage": mask_image_encoded} if mask_image_encoded not in [None, ""] else {}),
            **({"maskPrompt": mask_prompt} if mask_prompt not in [None, ""] else {}),
            **({"text": text} if text not in [None, ""] else {"text": " "}), 
            **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
        }
    except Exception as e:
        custom_log(f"[{datetime.now()}] Error constructing out_painting_params: {e}")
        return None, gr.update(visible=True, value=f"Error constructing out_painting_params: {e}")

    
    body = build_request("OUTPAINTING", out_painting_params, height, width, quality, cfg_scale, seed)
    custom_log(f"[{datetime.now()}] Calling generate_image for OUTPAINTING...")
    result = generate_image(body)
    custom_log(f"[{datetime.now()}] generate_image call finished.")
    images, errorbox = check_return(result)
    custom_log(f"[{datetime.now()}] --- outpainting END ---")
    return images[0], errorbox

def image_variation(images, text=None, negative_text=None, similarity_strength=0.5, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    custom_log(f"[{datetime.now()}] --- image_variation START ---")
    encoded_images = []
    custom_log(f"[{datetime.now()}] Processing input images...")
    for image_path in images:
        # Assuming image_path is the path string from Gradio File component
        global ENABLE_NSFW_CHECK
        ENABLE_NSFW_CHECK = True
        value = process_and_encode_image(image_path) # Pass path directly

        if len(value) < 200:
            custom_log(f"[{datetime.now()}] Error processing image {image_path}: {value}")
            custom_log(f"[{datetime.now()}] --- image_variation END (Error) ---")
            return None, gr.update(visible=True, value=value)
        encoded_images.append(value)
    custom_log(f"[{datetime.now()}] Finished processing input images.")

    image_variation_params = {
        "images": encoded_images,
        **({"similarityStrength": similarity_strength} if similarity_strength not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("IMAGE_VARIATION", image_variation_params, height, width, quality, cfg_scale, seed)
    custom_log(f"[{datetime.now()}] Calling generate_image for IMAGE_VARIATION...")
    result = generate_image(body)
    custom_log(f"[{datetime.now()}] generate_image call finished.")
    images, errorbox = check_return(result)
    custom_log(f"[{datetime.now()}] --- image_variation END ---")
    return images[0], errorbox

def image_conditioning(condition_image, text, negative_text=None, control_mode="CANNY_EDGE", control_strength=0.7, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    custom_log(f"[{datetime.now()}] --- image_conditioning START ---")
    custom_log(f"[{datetime.now()}] Processing condition image...")
    global ENABLE_NSFW_CHECK
    ENABLE_NSFW_CHECK = True
    condition_image_encoded = process_and_encode_image(condition_image)

    if len(condition_image_encoded) < 200:
        custom_log(f"[{datetime.now()}] Error processing condition image: {condition_image_encoded}")
        custom_log(f"[{datetime.now()}] --- image_conditioning END (Error) ---")
        return None, gr.update(visible=True, value=condition_image_encoded)
    custom_log(f"[{datetime.now()}] Finished processing condition image.")

    text_to_image_params = {
        "text": text,
        "controlMode": control_mode,
        "controlStrength": control_strength,
        "conditionImage": condition_image_encoded,
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }
    # Note: Image Conditioning uses TEXT_IMAGE task type
    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed)
    custom_log(f"[{datetime.now()}] Calling generate_image for IMAGE_CONDITIONING (using TEXT_IMAGE task)...")
    result = generate_image(body)
    custom_log(f"[{datetime.now()}] generate_image call finished.")
    images, errorbox = check_return(result)
    custom_log(f"[{datetime.now()}] --- image_conditioning END ---")
    return images[0], errorbox

def color_guided_content(text=None, reference_image=None, negative_text=None, colors=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    custom_log(f"[{datetime.now()}] --- color_guided_content START ---")
    reference_image_encoded = None # Initialize to None

    if reference_image is not None: # Check if it's actually provided
        custom_log(f"[{datetime.now()}] Processing reference image...")
        global ENABLE_NSFW_CHECK
        ENABLE_NSFW_CHECK = True
        reference_image_encoded = process_and_encode_image(reference_image)

        if len(reference_image_encoded) < 200:
            custom_log(f"[{datetime.now()}] Error processing reference image: {reference_image_encoded}")
            custom_log(f"[{datetime.now()}] --- color_guided_content END (Error) ---")
            return None, gr.update(visible=True, value=reference_image_encoded)
        custom_log(f"[{datetime.now()}] Finished processing reference image.")

    if not colors:
        custom_log(f"[{datetime.now()}] No colors provided, using default.")
        colors = "#FF5733,#33FF57,#3357FF,#FF33A1,#33FFF5,#FF8C33,#8C33FF,#33FF8C,#FF3333,#33A1FF"

    color_guided_generation_params = {
        "text": text,
        "colors": [color.strip() for color in colors.split(',')],
         # Use the encoded string if it exists
        **({"referenceImage": reference_image_encoded} if reference_image_encoded is not None else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("COLOR_GUIDED_GENERATION", color_guided_generation_params, height, width, quality, cfg_scale, seed)
    custom_log(f"[{datetime.now()}] Calling generate_image for COLOR_GUIDED_GENERATION...")
    result = generate_image(body)
    custom_log(f"[{datetime.now()}] generate_image call finished.")
    images, errorbox = check_return(result)
    custom_log(f"[{datetime.now()}] --- color_guided_content END ---")
    return images[0], errorbox

def background_removal(image):
    custom_log(f"[{datetime.now()}] --- background_removal START ---")
    custom_log(f"[{datetime.now()}] Processing input image...")
    global ENABLE_NSFW_CHECK
    ENABLE_NSFW_CHECK = True
    input_image = process_and_encode_image(image)

    if len(input_image) < 200:
        custom_log(f"[{datetime.now()}] Error processing input image: {input_image}")
        custom_log(f"[{datetime.now()}] --- background_removal END (Error) ---")
        return None, gr.update(visible=True, value=input_image)
    custom_log(f"[{datetime.now()}] Finished processing input image.")

    body = json.dumps({
        "taskType": "BACKGROUND_REMOVAL",
        "backgroundRemovalParams": {
            "image": input_image
        }
    })
    custom_log(f"[{datetime.now()}] Calling generate_image for BACKGROUND_REMOVAL...")
    result = generate_image(body)
    custom_log(f"[{datetime.now()}] generate_image call finished.")
    images, errorbox = check_return(result)
    custom_log(f"[{datetime.now()}] --- background_removal END ---")
    return images[0], errorbox

def generate_nova_prompt(origin_prompt: str):
    custom_log(f"[{datetime.now()}] --- generate_nova_prompt START ---")
    try:
        # custom_log(f"[{datetime.now()}] Reading seeds file...")
        # with open('seeds.json', 'r') as file:
        #     data = json.load(file)
        # if 'seeds' not in data or not isinstance(data['seeds'], list):
        #     custom_log(f"[{datetime.now()}] Invalid seeds file format.")
        #     raise ValueError("The JSON file must contain a 'seeds' key with a list of strings.")
        # custom_log(f"[{datetime.now()}] Seeds file read successfully.")

        # random_string = random.choice(data['seeds'])
        # custom_log(f"[{datetime.now()}] Selected random seed concept: {random_string}")
        prompt = f"""
            Optimize a creative image prompt that is: "{origin_prompt}"

            # Requirements:
            - Create a new, expanded prompt without mentioning or repeating the original prompt
            - Do not include any meta-instructions or seed references
            - You MUST ensure that you follow `Essential elements of good prompts` instructions when writing and refining image generation prompts

            # Essential elements of good prompts
            A good prompt serves as a descriptive image caption rather than command-based instructions. 
            It should provide enough detail to clearly describe the desired outcome while maintaining brevity (limited to 1,024 characters).
            Instead of giving command-based instructions like “Make a beautiful sunset,” you can achieve better results by describing the scene as if you’re looking at it: “A vibrant sunset over mountains, with golden rays streaming through pink clouds, captured from a low angle.”
            Think of it as painting a vivid picture with words to guide the model effectively.

            Effective prompts start by clearly defining the main subject and action:
            - Subject: Clearly define the main subject of the image. Example: “A blue sports car parked in front of a grand villa.”
            - Action or pose: Specify what the subject is doing or how it is positioned. Example: “The car is angled slightly towards the camera, its doors open, showcasing its sleek interior.”

            Add further context:
            - Environment: Describe the setting or background. Example: “A grand villa overlooking Lake Como, surrounded by manicured gardens and sparkling lake waters.”

            Once the main focus of the image is defined, you can refine the prompt further by specifying additional attributes such as visual style, framing, lighting, and technical parameters.
            For instance:
            - Lighting: Include lighting details to set the mood. Example: “Soft, diffused lighting from a cloudy sky highlights the car’s glossy surface and the villa’s stone facade.”
            - Camera position and framing: Provide information about perspective and composition. Example: “A wide-angle shot capturing the car in the foreground and the villa’s grandeur in the background, with Lake Como visible beyond.”
            - Style: Mention the visual style or medium. Example: “Rendered in a product photography style with vivid, high-contrast details.”

            Avoid using negation words like “no,” “not,” or “without” because they might lead to unintended consequences.
            
            # Examples
            Following are examples of the enhancement:
            Origin: A car in front of a house
            Enhanced: A blue luxury sports car parked in front of a grand villa overlooking Lake Como. The setting features meticulously manicured gardens, with the lake’s sparkling waters and distant mountains in the background. The car’s sleek, polished surface reflects the surrounding elegance, enhanced by soft, diffused lighting from a cloudy sky. A wide-angle shot capturing the car, villa, and lake in harmony, rendered in a cinematic style with vivid, high-contrast details.
            
            Following are good prompts:
            1. Aerial view of sparse arctic tundra landscape, expansive white terrain with meandering frozen rivers and scattered rock formations. High-contrast black and white composition showcasing intricate patterns of ice and snow, emphasizing texture and geological diversity. Bird’s-eye perspective capturing the abstract beauty of the arctic wilderness.	
            2. An overhead shot of premium over-ear headphones resting on a reflective surface, showcasing the symmetry of the design. Dramatic side lighting accentuates the curves and edges, casting subtle shadows that highlight the product’s premium build quality.
            3. An angled view of a premium matte metal water bottle with bamboo accents, showcasing its sleek profile. The background features a soft blur of a serene mountain lake. Golden hour sunlight casts a warm glow on the bottle’s surface, highlighting its texture. Captured with a shallow depth of field for product emphasis.
            4. Watercolor scene of a cute baby dragon with pearlescent mint-green scales crouched at the edge of a garden puddle, tiny wings raised. Soft pastel flowers and foliage frame the composition. Loose, wet-on-wet technique for a dreamy atmosphere, with sunlight glinting off ripples in the puddle.
            5. Abstract figures emerging from digital screens, glitch art aesthetic with RGB color shifts, fragmented pixel clusters, high contrast scanlines, deep shadows cast by volumetric lighting	
            6. An intimate portrait of a seasoned fisherman, his face filling the frame. His thick gray beard is flecked with sea spray, and his knit cap is pulled low over his brow. The warm glow of sunset bathes his weathered features in golden light, softening the lines of his face while still preserving the character earned through years at sea. His eyes reflect the calm waters of the harbor behind him.

            # Response Format:
            Just the new prompt text, nothing else
            """
        messages = [
            {"role": "user", "content": [{"text": prompt}]}
        ]

        custom_log(f"[{datetime.now()}] Calling generate_prompt (Bedrock converse)...")
        result = generate_prompt(messages) # Assuming generate_prompt handles the list of messages
        custom_log(f"[{datetime.now()}] generate_prompt call finished.")
        custom_log(f"[{datetime.now()}] --- generate_nova_prompt END ---")
        return result
    except Exception as e:
        custom_log(f"[{datetime.now()}] Error in generate_nova_prompt: {e}")
        custom_log(f"[{datetime.now()}] --- generate_nova_prompt END (Error) ---")
        # Return an error message suitable for Gradio Textbox output
        return f"Error generating prompt: {str(e)}"