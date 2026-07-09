# FPGA-Based FMCW Radar Time-to-Digital Converter with Dual-Phase Metastability Mitigation and Calibration Techniques

## Abstract

This paper presents a high-resolution FPGA-based time-to-digital converter (TDC) for FMCW radar applications. The proposed architecture employs a carry-chain delay line implemented in Xilinx FPGA fabric and introduces a dual-phase coarse timestamping method using 0° and 180° clock phases to mitigate metastability-induced timestamp ambiguity. Two static calibration methods are investigated and compared: deterministic delay characterization using MMCM dynamic phase shifting and statistical calibration using a ring oscillator. Furthermore, an online dynamic calibration framework is proposed to compensate for delay variations caused by temperature and process drift during operation. Experimental results obtained on a Xilinx Zynq platform demonstrate improved timestamp stability and enhanced fine-time linearity compared with conventional single-clock TDC architectures.

**Keywords:** FPGA, TDC, FMCW Radar, Carry Chain, Metastability, Dynamic Phase Shift, Ring Oscillator, Online Calibration

---

# 1. Introduction

Time-to-Digital Converters (TDCs) are essential components in applications requiring high-resolution time interval measurements, such as FMCW radar, LiDAR, time-of-flight imaging, and scientific instrumentation.

Recent FPGA devices provide dedicated carry-chain resources that enable efficient implementation of delay-line-based TDCs with picosecond-level resolution. Compared with ASIC-based implementations, FPGA TDCs offer lower development cost and greater design flexibility.

However, several challenges remain:

- Metastability around sampling clock boundaries
- Non-uniform carry-chain delays
- Process-Voltage-Temperature (PVT) variation
- Long-term timing drift

To address these challenges, this paper proposes a novel FPGA TDC architecture featuring:

1. Dual-phase coarse timestamping using 0° and 180° clocks
2. Static calibration using MMCM dynamic phase shifting
3. Statistical calibration using a ring oscillator
4. Online dynamic calibration for temperature compensation

The proposed method significantly improves timestamp robustness and calibration accuracy while maintaining low hardware complexity.

---

# 2. TDC Structure

## 2.1 Overall Architecture

The proposed TDC consists of:

- Carry-chain delay line
- Tap sampling registers
- Fine-time encoder
- Dual-phase coarse counters
- Calibration LUT
- Timestamp reconstruction module

```text
                 HIT
                  │
                  ▼
        +-------------------+
        | Carry Chain Delay |
        +-------------------+
                  │
                  ▼
        +-------------------+
        | Tap Sampler       |
        +-------------------+
                  │
                  ▼
        +-------------------+
        | Fine Encoder      |
        +-------------------+
                  │
                  ▼
        +-------------------+
        | Calibration LUT   |
        +-------------------+
                  │
                  ▼
        +-------------------+
        | Timestamp Builder |
        +-------------------+
```

---

## 2.2 Delay Line

The delay line is implemented using cascaded Xilinx CARRY4 primitives.

The number of taps is:

\[
N_{tap}=80\times4=320
\]

The delay chain covers more than one complete clock period of the 200 MHz sampling clock.

---

## 2.3 Fine Time Extraction

Unlike traditional transition detection approaches, the proposed implementation estimates signal propagation distance using tap population counting.

\[
FineIndex=\sum_{i=0}^{319} Tap_i
\]

The resulting fine index is converted into a physical delay value through a calibration lookup table.

---

## 2.4 Timestamp Reconstruction

The final timestamp is calculated as

\[
T_{abs}=T_{coarse}-T_{fine}
\]

where

\[
T_{coarse}=Counter\times T_{clk}
\]

and

\[
T_{fine}
\]

is obtained from the calibration LUT.

---

# 3. Metastability Mitigation Using Dual-Phase Clocking

## 3.1 Metastability Problem

Conventional carry-chain TDCs suffer from ambiguity when an input event arrives near a sampling clock boundary.

```text
Sampling Clock

------↑-----------↑-----------↑------

Hit Signal

-----------x-------------------------
           ▲

   Metastability Region
```

In this region:

- Fine-time measurement becomes unstable
- Coarse-counter selection may become ambiguous
- Timestamp discontinuity may occur

---

## 3.2 Proposed Dual-Phase Method

The proposed architecture maintains two independent coarse counters:

- Counter driven by 0° clock
- Counter driven by 180° clock

```text
0° Clock

---↑---------↑---------↑---------↑---

180° Clock

------↑---------↑---------↑---------↑
```

The second counter effectively observes the event with a half-period offset.

---

## 3.3 Danger Zone Detection

The propagation distance within the delay line indicates whether the event occurred near a clock boundary.

A danger zone is defined as

\[
FineIndex < T_L
\]

or

\[
FineIndex > T_H
\]

where:

\[
T_L=40
\]

\[
T_H=220
\]

When an event falls within the danger zone:

```verilog
if(danger_zone)
    coarse = coarse_180 + 1;
else
    coarse = coarse_0;
```

---

## 3.4 Advantages

The proposed method:

- Eliminates coarse timestamp ambiguity
- Reduces metastability-induced errors
- Requires minimal FPGA resources
- Avoids redundant TDC channels

---

# 4. Static Calibration Method: Dynamic Phase Shift vs Ring Oscillator

Since carry-chain delays are inherently non-uniform, calibration is necessary.

Two approaches are investigated.

---

## 4.1 MMCM Dynamic Phase Shift Calibration

A synchronous pulse generator is used while the MMCM gradually shifts the sampling clock.

```text
Reference Pulse
       │
       ▼

MMCM Dynamic Shift

0° → 360°
```

The resulting histogram directly represents tap widths.

### Advantages

- Deterministic
- Repeatable
- High accuracy

### Disadvantages

- Requires MMCM control logic
- Long calibration time

---

## 4.2 Ring Oscillator Calibration

A ring oscillator generates statistically distributed hit events.

```text
Ring Oscillator
       │
       ▼
Random Events
       │
       ▼
Histogram
```

Bin width is estimated from occupancy.

\[
W_i=
\frac{H_i}
{\sum H_i}
\times T_{clk}
\]

where:

- \(W_i\) = bin width
- \(H_i\) = measured count

### Advantages

- Simple implementation
- Low resource cost
- Continuous operation

### Disadvantages

- Requires many samples
- Statistical uncertainty exists

---

## 4.3 Comparison

| Item | Dynamic Phase Shift | Ring Oscillator |
|--------|--------|--------|
| Accuracy | High | Medium |
| Repeatability | Excellent | Good |
| Hardware Complexity | Medium | Low |
| Calibration Time | Long | Short |
| Production Calibration | Suitable | Suitable |
| Continuous Monitoring | Difficult | Easy |

---

# 5. Online Dynamic Calibration

## 5.1 Motivation

Static calibration removes manufacturing variation but cannot compensate for temperature drift.

The delay of a carry cell can be expressed as

\[
Delay=f(P,V,T)
\]

where:

- P = Process
- V = Supply Voltage
- T = Temperature

As temperature changes, the delay-line characteristics shift, causing timing errors.

---

## 5.2 Proposed Online Calibration

A reference ring oscillator is continuously monitored.

```text
Temperature Change
         │
         ▼
 Ring Oscillator Frequency
         │
         ▼
 Delay Variation Estimate
         │
         ▼
 Calibration LUT Update
```

The scaling factor is calculated as

\[
K(T)=\frac{F_{ref}}{F_{RO}(T)}
\]

where:

- \(F_{ref}\) = calibration reference frequency
- \(F_{RO}(T)\) = measured ring oscillator frequency

The LUT is updated as

\[
LUT_{new}=K(T)\times LUT_{nominal}
\]

This allows compensation without interrupting normal TDC operation.

---

# 6. Test Results

## 6.1 Experimental Platform

| Parameter | Value |
|------------|----------|
| FPGA Device | Xilinx Zynq-7000 |
| Clock Frequency | 200 MHz |
| Delay Taps | 320 |
| Delay Structure | CARRY4 Chain |
| Coarse Counter | Dual Phase |

---

## 6.2 Metastability Evaluation

Two configurations are compared:

1. Conventional single-clock TDC
2. Proposed dual-phase TDC

Measured metrics:

- Timestamp discontinuity
- Coarse-counter error rate
- Standard deviation

The proposed architecture significantly reduces boundary-related timestamp errors.

---

## 6.3 Static Calibration Evaluation

The following methods are compared:

- MMCM Phase Sweep Calibration
- Ring Oscillator Calibration

Measured metrics:

- Differential Non-Linearity (DNL)
- Integral Non-Linearity (INL)
- RMS Resolution

---

## 6.4 Temperature Drift Evaluation

Temperature range:

\[
25^\circ C \sim 85^\circ C
\]

Configurations:

1. No calibration
2. Static calibration only
3. Online dynamic calibration

Measured metrics:

- DNL
- INL
- RMS timing resolution
- Long-term stability

---

# 7. Conclusion

This paper presented an FPGA-based carry-chain TDC architecture incorporating a dual-phase coarse timestamping method and multiple calibration strategies.

The proposed dual-phase architecture uses 0° and 180° clocks to eliminate coarse-counter ambiguity near clock boundaries and significantly reduce metastability-induced timestamp errors.

Two static calibration approaches were investigated and compared: MMCM dynamic phase-shift calibration and ring oscillator statistical calibration. Additionally, an online calibration framework was proposed to compensate delay variation caused by temperature drift.

The proposed architecture provides a practical solution for high-resolution FMCW radar applications requiring robust timing performance under varying operating conditions.

---

# Contributions of This Work

1. Dual-phase (0°/180°) coarse timestamping for metastability mitigation.
2. Comparative study of MMCM dynamic phase-shift calibration and ring oscillator calibration.
3. Online dynamic calibration framework for temperature-dependent delay compensation.
4. FPGA implementation suitable for FMCW radar systems.