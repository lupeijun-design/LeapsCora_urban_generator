# LeapsCora_urban_generator
generate urban public space 

#### command to run all 
.\run_step1_to_step3_and_render.bat
#### command to run each generated step：
python generate_step1_network.py --input step1_test_input.json --settings default_network.yaml --output step1_generated_scene.json
python generate_step2_building.py --input step1_generated_scene.json --output step2_generated_scene.json --typology default_building.yaml
python generate_step3_keyPoint.py --input step2_generated_scene.json --output step3_generated_scene.json --typology default_keyPoint.yaml
python generate_step4_pedestrian_network.py --input step3_generated_scene.json --output step4_generated_scene.json --typology default_pedestrian_network.yaml
python generate_step5_pedestrian_space.py --input step4_generated_scene.json --output step5_generated_scene.json --typology defaults_pedestrian_space.yaml

#### command to render each generated result：
blender --render_step1_input.py -- step1_test_input.json
blender --python render_step1_result.py -- step1_generated_scene.json
blender --python render_step2_result.py -- step2_generated_scene.json
blender --python render_step3_result.py -- step3_generated_scene.json
blender --python render_step4_result.py -- step4_generated_scene.json
blender --python render_step5_result.py -- step5_generated_scene.json
