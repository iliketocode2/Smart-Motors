from machine import Pin, SoftI2C, PWM, ADC, Timer
import time
import random
import icons

# Hardware setup (based on your existing code)
i2c = SoftI2C(scl = Pin(7), sda = Pin(6))
display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))

# Button setup
switch_down = Pin(8, Pin.IN)
switch_select = Pin(9, Pin.IN)
switch_up = Pin(10, Pin.IN)

# Game state variables
game_state = "menu"  # "menu", "playing", "won", "lost"
target_number = 0
current_guess = 50
last_guess = 0
attempts_left = 7
max_attempts = 7
game_range_min = 1
game_range_max = 100

# Button state tracking
switch_state_up = False
switch_state_down = False
switch_state_select = False
last_switch_state_up = False
last_switch_state_down = False
last_switch_state_select = False
switched_up = False
switched_down = False
switched_select = False
last_pressed = 0

def check_switch(p):
    """Handle button state changes with debouncing"""
    global switch_state_up, switch_state_down, switch_state_select
    global switched_up, switched_down, switched_select
    global last_switch_state_up, last_switch_state_down, last_switch_state_select
    
    switch_state_up = switch_up.value()
    switch_state_down = switch_down.value()
    switch_state_select = switch_select.value()
         
    if switch_state_up != last_switch_state_up:
        switched_up = True
    elif switch_state_down != last_switch_state_down:
        switched_down = True
    elif switch_state_select != last_switch_state_select:
        switched_select = True
                
    if switched_up and switch_state_up == 0:
        handle_up_button()
        switched_up = False
    elif switched_down and switch_state_down == 0:
        handle_down_button()
        switched_down = False
    elif switched_select and switch_state_select == 0:
        handle_select_button()
        switched_select = False
    
    last_switch_state_up = switch_state_up
    last_switch_state_down = switch_state_down
    last_switch_state_select = switch_state_select

def handle_up_button():
    """Handle up button press based on game state"""
    global current_guess, last_pressed
    
    if time.ticks_ms() - last_pressed < 200:  # Debounce
        return
    last_pressed = time.ticks_ms()
    
    if game_state == "playing":
        current_guess = min(game_range_max, current_guess + 1)
        display_game_screen()
    elif game_state in ["won", "lost"]:
        reset_game()

def handle_down_button():
    """Handle down button press based on game state"""
    global current_guess, last_pressed
    
    if time.ticks_ms() - last_pressed < 200:  # Debounce
        return
    last_pressed = time.ticks_ms()
    
    if game_state == "playing":
        current_guess = max(game_range_min, current_guess - 1)
        display_game_screen()
    elif game_state in ["won", "lost"]:
        reset_game()

def handle_select_button():
    """Handle select button press based on game state"""
    global game_state, target_number, attempts_left, last_pressed
    
    if time.ticks_ms() - last_pressed < 200:  # Debounce
        return
    last_pressed = time.ticks_ms()
    
    if game_state == "menu":
        start_new_game()
    elif game_state == "playing":
        make_guess()
    elif game_state in ["won", "lost"]:
        reset_game()

def start_new_game():
    """Initialize a new game"""
    global game_state, target_number, current_guess, attempts_left, last_guess
    
    game_state = "playing"
    target_number = random.randint(game_range_min, game_range_max)
    current_guess = (game_range_min + game_range_max) // 2
    last_guess = 0
    attempts_left = max_attempts
    
    print(f"DEBUG: Target number is {target_number}")  # Remove in final version
    display_game_screen()

def make_guess():
    """Process the current guess"""
    global game_state, attempts_left, last_guess
    
    last_guess = current_guess
    attempts_left -= 1
    
    if current_guess == target_number:
        game_state = "won"
        display_win_screen()
    elif attempts_left <= 0:
        game_state = "lost"
        display_lose_screen()
    else:
        display_game_screen()

def reset_game():
    """Reset to main menu"""
    global game_state
    game_state = "menu"
    display_menu()

def display_menu():
    """Display the main menu screen"""
    display.fill(0)
    
    # Title
    display.text("NUMBER GUESSER", 10, 5)
    display.text("==============", 10, 15)
    
    # Instructions
    display.text("Guess 1-100", 25, 28)
    display.text("7 attempts", 28, 38)
    
    # Start button
    display.text("SELECT: START", 15, 52)
    
    display.show()

def display_game_screen():
    """Display the main game screen"""
    display.fill(0)
    
    # Current guess (centered)
    guess_str = str(current_guess)
    x_pos = 64 - (len(guess_str) * 4)  # Center the text
    display.text(f"Guess: {guess_str}", x_pos - 30, 15)
    
    # Attempts left
    display.text(f"Tries: {attempts_left}", 5, 5)
    
    # Last guess feedback (only show after first guess)
    if attempts_left < max_attempts:
        if target_number > last_guess:
            display.text("TOO LOW!", 35, 35)
        elif target_number < last_guess:
            display.text("TOO HIGH!", 30, 35)
    
    # Controls
    display.text("UP/DOWN: Change", 5, 45)
    display.text("SELECT: Guess", 10, 55)
    
    display.show()

def display_win_screen():
    """Display win screen"""
    display.fill(0)
    
    # Victory message
    display.text("YOU WON!", 30, 10)
    display.text("=========", 30, 20)
    
    # Stats
    used_attempts = max_attempts - attempts_left
    display.text(f"Number: {target_number}", 25, 30)
    display.text(f"Attempts: {used_attempts}", 20, 40)
    
    # Continue instruction
    display.text("ANY KEY: Menu", 15, 55)
    
    display.show()

def display_lose_screen():
    """Display lose screen"""
    display.fill(0)
    
    # Game over message
    display.text("GAME OVER", 25, 10)
    display.text("=========", 25, 20)
    
    # Reveal answer
    display.text(f"Answer: {target_number}", 25, 30)
    display.text("Better luck", 25, 40)
    display.text("next time!", 28, 50)
    
    # Continue instruction  
    display.text("ANY KEY: Menu", 15, 58)
    
    display.show()

# Initialize timer for button checking
tim = Timer(0)
tim.init(period=50, mode=Timer.PERIODIC, callback=check_switch)

# Welcome message
display.fill(0)
display.text("SmartMotor", 25, 20)
display.text("Games", 40, 30)
display.text("Loading...", 30, 45)
display.show()
time.sleep(2)

# Start with menu
display_menu()

# Main game loop
while True:
    time.sleep(0.1)  # Small delay to prevent excessive CPU usage
    
    # The main logic is handled by interrupts and button callbacks
    # This loop just keeps the program running
    pass
