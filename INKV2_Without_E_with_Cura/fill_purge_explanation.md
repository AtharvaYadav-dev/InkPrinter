# E-Value, Fill & Purge Operations in InkPrinter

Namaste! Is document mein hum samjhenge ki aapke **InkPrinter** setup mein **E value** ka kya importance hai, **Fill aur Purge** operations actually backend (MCU/Arduino) par kaise kaam karte hain, aur hum E parameter ya Cura ke bina same result kaise achieve kar sakte hain.

---

## 1. The Importance of E-Value (Extrusion Value)

G-code mein, `E` parameter ka matlab hota hai **Extrusion** (ya material flow). Jab Cura koi path generate karta hai (like `G1 X10 Y10 E0.5`), toh E value extruder stepper motor ko batata hai ki XY movement ke sath kitna material push karna hai.

### Cura mein E kaise calculate hota hai?
Cura material flow ko ek specific volume equation se nikalta hai:
- **Volume needed** = `Line Width` × `Layer Height` × `Travel Distance (XY)`
- Us volume ko extruder (filament diameter ya syringe diameter) ke mutabik linear distance (`E`) mein convert kiya jata hai.

**Kyun Zaroori Hai?**
- E value material extrusion aur toolhead ki movement speed ko synchronize karta hai, taaki over-extrusion ya under-extrusion na ho.
- Agar galti se E value galat ho, toh ink fail sakti hai (blobbing) ya lines toot sakti hain (gaps).

---

## 2. Working of 'Fill' and 'Purge' Operations

Aapke `sketchpurge.ino` code ke according, **FILL** aur **PURGE** ke backend calculations bahut seedhe aur precise hain.

### Calculations done at MCU:
Jab MCU ko serial command milta hai jaise `FILL 10.5` ya `PURGE 5.0`, toh yeh steps follow hote hain:

1. **Direction Set Hoti Hai:**
   - **FILL:** Motor aage ghoomti hai (`DIR_PIN = HIGH`) ink push karne ke liye.
   - **PURGE:** Motor pichhe ghoomti hai (`DIR_PIN = LOW`) pressure release karne ya ink waapis kheenchna (retraction) ke liye.

2. **Step Calculation:**
   Code mein ek constant set hai: `#define STEPS_PER_MM 2560`.
   - Formula: `Total Pulses = Distance (mm) × STEPS_PER_MM`
   - Example: Agar command hai `FILL 2.0`, toh `2.0 × 2560 = 5120 pulses`.
   - *Fractional distances* ko bhi sambhala gaya hai (floating point remainder store karke next command mein add kar diya jata hai taaki accuracy loss na ho).

3. **Timer Interrupt:**
   Hardware timer har 150 microseconds mein trigger hota hai (StepTimerISR), aur utne steps motor ko bhejta hai jab tak `targetPulses` zero na ho jaye.

---

## 3. What if we don't want to use the 'E' parameter?

**Haan, hum bina E parameter ke bhi same extrusion calculations achieve kar sakte hain!**

Agar aap `E` parameter skip karna chahte hain, toh extrusion ko **Time-based** ya **Direct Command-based** banaya jaa sakta hai. 
- **Constant Flow Method:** Agar XY speed constant ho, toh aap ek external pump ya motor ko continuous flow pe chhod sakte hain (e.g., motor ON jab tool down, motor OFF jab tool up). `E` parameter step-by-step control ke liye hota hai, lekin continuous line ke liye hum sirf start aur stop commands use kar sakte hain.

---

## 4. Can we get the same output without using Cura?

**Bilkul Possible Hai!** Aur aapke software mein actually aise scripts maujood bhi hain (jaise `svg_to_gcode.py`, `dxf_to_gcode.py`).

Cura ek **Slicer** hai, jiska main kaam 3D models (STL) ko layers (Z-axis) aur 2D paths (G-code) mein todna hai. Lekin agar aap directly 2D designs (SVG, DXF, PNG, BMP) print kar rahe hain, toh Cura ki zaroorat hi nahi hai.

### How to do it manually (Without Cura):

1. **Vector Conversion (SVG/DXF to G-code):**
   Aap directly SVG ya DXF file se lines/curves (paths) extract kar sakte hain (Python libraries like `svgpathtools` ya `ezdxf` ka use karke).

2. **Generate G-Code Paths:**
   In curves ko chhote chhote line segments (X, Y points) mein tod dein.
   
3. **Extrusion Control (The alternative to Cura):**
   Continuous flow ke liye, bas start aur stop commands lagayein:
   ```python
   # Simple Python snippet
   
   # G-code likhna
   gcode_line = f"M106 ; Motor ON\nG1 X{x2:.3f} Y{y2:.3f}\nM107 ; Motor OFF"
   ```
4. **Z-Hop / Pen Up & Down:**
   Har shape ke shuru mein toolhead ko niche laayein (`G0 Z0`), aur end mein upar utha lein (`G0 Z5`) - theek waise hi jaise ek pen plotta karta hai.

**Summary:** 
Aap bilkul apna custom slicer ya path generator bana sakte hain. Actually, 2D ink printing (Pen plotting ya Syringe extrusion) ke liye custom Python scripts Cura se zyada better control aur accuracy dete hain kyunki Cura 3D plastic filaments ke hisaab se optimized hota hai, jabki ink flow dynamics alag hote hain.
