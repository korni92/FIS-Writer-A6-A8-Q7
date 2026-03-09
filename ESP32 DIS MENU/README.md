To do:

adding diconnect to main and ui_main if the handshake fails, they dont continou sending data. using bool tacho_connected = false;
at the moment dont power car and ESP32 at the same time, otherwise it will cause a loop where it wants ACK from cluster.

Use ESP32-C6 with SN65HVD230 transivers for both sides. 

MMI CAN -> RX 19, TX 18
Ckuster CAN -> RX 11, TX 10
