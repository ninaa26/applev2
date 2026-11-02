// Setting an SX1262 up for the link (RadioLib 7), shared by the camera and the hub's bridge so both ends always
// match. The frame layout is in sentinel_radio.h.
#pragma once
#include <RadioLib.h>
#include "sentinel_radio.h"

// Returns a RadioLib status (0: ready to listen). rxen/txen: GPIOs driving the module's RF switch, or -1 to let
// the SX1262's DIO2 drive it (the Core1262 and E22 modules: DIO2 is wired to their switch). The TCXO is tried
// at RADIO_TCXO_V first and, if the chip won't start with it, as a plain crystal; *tcxo says which worked.
static int16_t radioSetup(SX1262 &radio, void (*dio1)(void), int rxen, int txen, float *tcxo) {
  float v = RADIO_TCXO_V;
  int16_t st = radio.beginFSK(RADIO_FREQ_MHZ, RADIO_BITRATE_KBPS, RADIO_DEVIATION_KHZ, RADIO_RX_BW_KHZ,
                              RADIO_POWER_DBM, RADIO_PREAMBLE_BITS, v, false);
  if (st != RADIOLIB_ERR_NONE && v > 0) {
    v = 0;
    st = radio.beginFSK(RADIO_FREQ_MHZ, RADIO_BITRATE_KBPS, RADIO_DEVIATION_KHZ, RADIO_RX_BW_KHZ,
                        RADIO_POWER_DBM, RADIO_PREAMBLE_BITS, v, false);
  }
  if (st != RADIOLIB_ERR_NONE) return st;
  if (tcxo) *tcxo = v;
  if (rxen >= 0 || txen >= 0) {
    radio.setRfSwitchPins(rxen >= 0 ? rxen : RADIOLIB_NC, txen >= 0 ? txen : RADIOLIB_NC);
  } else if ((st = radio.setDio2AsRfSwitch(true)) != RADIOLIB_ERR_NONE) {
    return st;
  }
  uint8_t sync[sizeof(RADIO_SYNC)];
  memcpy(sync, RADIO_SYNC, sizeof(sync));
  if ((st = radio.setSyncWord(sync, sizeof(sync))) != RADIOLIB_ERR_NONE) return st;
  if ((st = radio.setCRC(2)) != RADIOLIB_ERR_NONE) return st;
  if ((st = radio.setDataShaping(RADIOLIB_SHAPING_0_5)) != RADIOLIB_ERR_NONE) return st;
  if ((st = radio.setWhitening(true)) != RADIOLIB_ERR_NONE) return st;
  if ((st = radio.variablePacketLengthMode(MAX_FRAME)) != RADIOLIB_ERR_NONE) return st;
  radio.setDio1Action(dio1);
  return RADIOLIB_ERR_NONE;
}
