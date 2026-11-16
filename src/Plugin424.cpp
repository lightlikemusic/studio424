// STUDIO424 - a cassette four-track mixer channel strip for MPC, by Lightlike
//
// Signal flow (per channel, stereo-linked controls):
//
//   in -> Trim (input gain) -> preamp stage (gentle asymmetric soft clip)
//      -> 20 Hz coupling high-pass (also removes DC from the asymmetry)
//      -> High shelf 10 kHz (+/-10 dB)
//      -> Low shelf 100 Hz (+/-10 dB)
//      -> op-amp ceiling (soft limit around +9 dBFS)
//      -> Channel fader (a knob here; 0..10 scale, 7.5 = unity)
//      -> mix bus summing amp (same soft ceiling)
//      -> Master fader (0..10 scale, 7.5 = unity) -> out
//
// Bypass is left to the MPC's own insert bypass.
//
// Two-band EQ, as on the original early-90s four-track cassette mixer channel
// (later revisions added a sweepable mid; this one does not). Shelf frequencies
// and ranges follow the published spec; the slope is an estimate (Q 0.55).
//
// There is no tape or noise-reduction model: this is the mixer channel only.

#include "mpc_plugin.h"
#include "dsp/biquad.h"
#include "dsp/math.h"

#include <atomic>
#include <cmath>
#include <cstdio>

namespace {

enum ParamIndex
{
    kChannel = 0, // channel fader 0..10 (7.5 = 0 dB). Index 0: harmless when nudged.
                  // (id "level": it was the only fader before Master was added)
    kTrim,        // dB of input gain into the preamp stage
    kHigh,        // dB, 10 kHz shelf
    kLow,         // dB, 100 Hz shelf
    kMaster,      // master fader 0..10 (7.5 = 0 dB), after the mix bus
    kNumParams
};

constexpr int   kMaxChannels = 2;
constexpr float kHighHz      = 10000.0f;
constexpr float kLowHz       = 100.0f;
constexpr float kShelfQ      = 0.55f;
constexpr float kHpfHz       = 20.0f;

// Preamp: x*gain -> tanh(drive*x + bias) - tanh(bias), normalised so small
// signals pass at unity. The bias gives a little even-harmonic colour that
// grows as Trim pushes the stage.
constexpr float kPreDrive = 0.35f;
constexpr float kPreBias  = 0.15f;

// Op-amp output ceiling (linear). 2.8 ~ +9 dBFS.
constexpr float kCeiling  = 2.8f;

// Fader law: 0..10 scale. 10 = +10 dB, 7.5 = 0 dB, 5 = -10 dB, then steeper
// down to -60 dB at 0.5 and silence at 0.
float faderToDb(float v)
{
    if (v >= 5.0f) return (v - 7.5f) * 4.0f;
    return -10.0f - (5.0f - v) * (50.0f / 4.5f);
}

float faderToGain(float v)
{
    if (v <= 0.5f) return v <= 0.0f ? 0.0f : (v / 0.5f) * mpc::dsp::dbToGain(-60.0f);
    return mpc::dsp::dbToGain(faderToDb(v));
}

} // namespace

class Plugin424 : public mpc::Plugin
{
public:
    Plugin424() : mpc::Plugin(makeInfo())
    {
        addParam(mpc::floatParam("level",   "Channel",  0.0f,   10.0f,   7.5f,    "",   1));
        addParam(mpc::floatParam("trim",    "Trim",     -10.0f, 20.0f,   0.0f,    "dB", 1));
        addParam(mpc::floatParam("high",    "High",     -10.0f, 10.0f,   0.0f,    "dB", 1));
        addParam(mpc::floatParam("low",     "Low",      -10.0f, 10.0f,   0.0f,    "dB", 1));
        addParam(mpc::floatParam("master",  "Master",   0.0f,   10.0f,   7.5f,    "",   1));

        //                         Chan  Trim   High   Low   Master
        addProgram("Flat",          {7.5f,  0.0f,  0.0f,  0.0f, 7.5f});
        addProgram("Warm Bus",      {8.5f,  4.0f, -2.0f,  3.0f, 6.5f});
        addProgram("Hot Trim",      {6.5f, 14.0f,  1.0f,  2.0f, 7.5f});
        addProgram("Vocal Forward", {7.5f,  3.0f,  4.0f, -3.0f, 7.5f});
        addProgram("Fat Drums",     {9.0f, 10.0f, -3.0f,  5.0f, 6.0f});
        addProgram("Thin Lo-Fi",    {8.0f,  8.0f, -8.0f, -10.f, 7.5f});
    }

    void prepare(double sampleRate, int maxBlockSize) override
    {
        (void)maxBlockSize;
        sampleRate_ = (float)sampleRate;
        hpf_.setCoeffs(mpc::dsp::BiquadCoeffs::highpass(sampleRate, kHpfHz, 0.7071f));
        reset();
    }

    void reset() override
    {
        for (int ch = 0; ch < kMaxChannels; ++ch)
        {
            hpfCh_[ch].reset(); high_[ch].reset(); low_[ch].reset();
        }
        trimDb_ = get(kTrim); highDb_ = get(kHigh); lowDb_ = get(kLow);
        updateCoeffs(true);
        trimGain_ = mpc::dsp::dbToGain(trimDb_);
        level_    = faderToGain(get(kChannel));
        master_   = faderToGain(get(kMaster));
        // reset() runs (on the audio thread) after a preset or state load: tell the
        // MPC every value changed, or its screen and Q-Links keep the old positions.
        reportAllPending_.store(true, std::memory_order_release);
    }

    void process(mpc::ProcessContext& ctx) override
    {
        const int n           = ctx.numFrames;
        const int numChannels = mpc::clamp(ctx.numOutputs, 0, kMaxChannels);
        if (n <= 0) return;

        // Block-rate smoothing of the EQ controls (~25 ms), then coefficients.
        const float blockSec = (float)n / sampleRate_;
        const float a = 1.0f - std::exp(-blockSec / 0.025f);
        trimDb_ += a * (get(kTrim)    - trimDb_);
        highDb_ += a * (get(kHigh)    - highDb_);
        lowDb_  += a * (get(kLow)     - lowDb_);
        updateCoeffs(false);

        // Per-sample ramps for gain stages (linear across the block).
        const float trimTarget  = mpc::dsp::dbToGain(trimDb_);
        const float levelTarget  = faderToGain(get(kChannel));
        const float masterTarget = faderToGain(get(kMaster));
        const float inv  = 1.0f / (float)n;
        const float dTrim  = (trimTarget - trimGain_) * inv;
        const float dLevel = (levelTarget - level_) * inv;
        const float dMaster = (masterTarget - master_) * inv;

        const float biasOffset = mpc::dsp::fastTanh(kPreBias);
        // 1 / (drive * slope at the bias point) -> exact unity gain for small signals.
        const float invDrive   = 1.0f / (kPreDrive * (1.0f - biasOffset * biasOffset));
        const float invCeil    = 1.0f / kCeiling;

        for (int i = 0; i < n; ++i)
        {
            trimGain_ += dTrim;
            level_    += dLevel;
            master_   += dMaster;

            for (int ch = 0; ch < numChannels; ++ch)
            {
                const float dry = (ctx.inputs != nullptr && ch < ctx.numInputs && ctx.inputs[ch] != nullptr)
                                      ? ctx.inputs[ch][i] : 0.0f;

                // Preamp stage.
                float x = dry * trimGain_;
                x = (mpc::dsp::fastTanh(x * kPreDrive + kPreBias) - biasOffset) * invDrive;
                x = hpfCh_[ch].process(x);

                // Two-band EQ.
                x = high_[ch].process(x);
                x = low_[ch].process(x);

                // Op-amp ceiling, then the channel fader.
                x = kCeiling * mpc::dsp::fastTanh(x * invCeil);
                x *= level_;

                // Mix bus summing amp, then the master fader.
                x = kCeiling * mpc::dsp::fastTanh(x * invCeil);
                x *= master_;

                ctx.outputs[ch][i] = x;
            }
        }
        trimGain_ = trimTarget;
        level_    = levelTarget;
        master_   = masterTarget;

        // After a preset/state load, report every parameter so the knobs and fader
        // move. The MPC's host queues audioMasterAutomate, so this is safe here.
        if (reportAllPending_.exchange(false, std::memory_order_acq_rel))
            for (int k = 0; k < kNumParams; ++k) notifyHostParameterChanged(k);
    }

    bool formatValue(int index, float plain, std::string& out) override
    {
        char buf[32];
        if (index == kChannel || index == kMaster)
        {
            if (plain <= 0.0f) { out = "-inf dB"; return true; }
            const float db = plain <= 0.5f ? -60.0f + 20.0f * std::log10(plain / 0.5f) : faderToDb(plain);
            std::snprintf(buf, sizeof buf, "%.1f  (%+.1f dB)", plain, db);
            out = buf;
            return true;
        }
        if (index == kTrim || index == kHigh || index == kLow)
        {
            std::snprintf(buf, sizeof buf, "%+.1f dB", plain);
            out = buf;
            return true;
        }
        return false;
    }

private:
    static mpc::PluginInfo makeInfo()
    {
        mpc::PluginInfo info;
        info.name         = "STUDIO424";
        info.vendor       = "Lightlike";
        info.uniqueId     = MPC_FOURCC(kUid[0], kUid[1], kUid[2], kUid[3]);
        info.version      = 1000;
        info.isInstrument = false;
        info.numInputs    = 2;
        info.numOutputs   = 2;
        info.tailSamples  = 1;
        return info;
    }

    static constexpr char kUid[5] = "LLpp";

    void updateCoeffs(bool force)
    {
        using mpc::dsp::BiquadCoeffs;
        const double sr = sampleRate_;
        if (force || std::fabs(highDb_ - cHighDb_) > 0.01f)
        {
            cHighDb_ = highDb_;
            const BiquadCoeffs c = BiquadCoeffs::highShelf(sr, mpc::clamp(kHighHz, 20.0f, 0.45f * sampleRate_), kShelfQ, highDb_);
            for (auto& f : high_) f.setCoeffs(c);
        }
        if (force || std::fabs(lowDb_ - cLowDb_) > 0.01f)
        {
            cLowDb_ = lowDb_;
            const BiquadCoeffs c = BiquadCoeffs::lowShelf(sr, kLowHz, kShelfQ, lowDb_);
            for (auto& f : low_) f.setCoeffs(c);
        }
        if (force)
            for (auto& f : hpfCh_) f.setCoeffs(hpf_.coeffs());
    }

    mpc::dsp::Biquad hpf_;   // holds the HPF coefficients
    mpc::dsp::Biquad hpfCh_[kMaxChannels];
    mpc::dsp::Biquad high_[kMaxChannels];
    mpc::dsp::Biquad low_[kMaxChannels];

    float sampleRate_ = 44100.0f;
    float trimDb_ = 0.0f, highDb_ = 0.0f, lowDb_ = 0.0f;
    float cHighDb_ = 0.0f, cLowDb_ = 0.0f;
    float trimGain_ = 1.0f, level_ = 1.0f, master_ = 1.0f;
    std::atomic<bool> reportAllPending_{false};
};

MPC_PLUGIN_ENTRY(Plugin424)
