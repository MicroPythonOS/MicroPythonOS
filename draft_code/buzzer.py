from machine import Pin, PWM
import time

# Set up pin 46 as PWM output
buzzer = PWM(Pin(46))

# Function to play a tone (frequency in Hz, duration in seconds)
def play_tone(frequency, duration):
    buzzer.freq(frequency)  # Set frequency
    buzzer.duty_u16(32768) # 50% duty cycle (32768 is half of 65536)
    time.sleep(duration)    # Play for specified duration
    buzzer.duty_u16(0)     # Stop the tone

# Example: Play a 440 Hz tone (A4 note) for 1 second
play_tone(440, 1)

# Optional: Play a sequence of notes
notes = [(261, 0.5), (293, 0.5), (329, 0.5), (349, 0.5)]  # C4, D4, E4, F4
for freq, duration in notes:
    play_tone(freq, duration)
    time.sleep(0.1)  # Short pause between notes

# Turn off the buzzer
buzzer.deinit()
