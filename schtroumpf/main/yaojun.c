#include <stdio.h>
#include <stdlib.h>


typedef struct Node_s {
	int data;
	struct Node_s *next;
}Node_t;

Node_t *Create(){
	// create a list of 5 nodes
	Node_t *Head, *p, *q;
	int i;
	Head = (Node_t *)malloc(sizeof(Node_t));
	q = Head;
	for (i = 0; i < 5; i++) {
		p = (Node_t *)malloc(sizeof(Node_t));
		if (!p) goto ERROR;
		p->data = i;
		p->next = NULL;
	        q->next = p;	
		q = p;
	}

        return Head;

	ERROR:
		q = Head;
		while(q) {
			p = q;
			free(q);
			q = p->next;
		}
		return NULL;
}

int main() {
	Node_t *Head  = Create();
	Node_t *x = Head->next;
	if (x) {
		while(x) {
			printf("%d\n", x->data);	
			x = x->next;
		}
	}
	
	return 0;
}
