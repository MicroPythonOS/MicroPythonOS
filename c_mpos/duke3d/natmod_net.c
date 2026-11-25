// The one symbol mmulti.c calls straight out of its UDP branch even when
// STUB_NETWORKING is 1. The badge core links the whole tree with duplicate
// definitions allowed; a native module cannot, so network.c's dispatchers
// cover the rest and this covers the direct call.
void unstable_callcommit(void) {
}
